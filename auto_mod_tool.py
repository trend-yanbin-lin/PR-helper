import os, json, subprocess, logging, requests, datetime, re
from langchain_openai import OpenAIEmbeddings
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import load_tools, initialize_agent, tool, AgentType
import requests
from typing import Annotated
from langchain_core.vectorstores import InMemoryVectorStore

# 初始化日誌紀錄器
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

GIT_API_HEADERS = {"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN')}", "Accept": "application/vnd.github+json"}

# 從環境變量讀取 GitHub 事件內容 (issue_comment payload)
with open(os.environ.get('GITHUB_EVENT_PATH'), 'r') as f:
    event = json.load(f)

UserQuery = "None"

embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_ENDPOINT_URL"), model="text-embedding-3-large")
filepath_map = {
    'youtube_dl': "youtube_dl.pkl",
    'sortedcollections': "sortedcollections.pkl",
    'codingStyle':  "https://trend-yanbin-lin.github.io/publish-style-guide/",
}

def extract_code_blocks(text):
    pattern = r"```[\w\s]*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return matches

@tool
def get_reference(name: Annotated[str, "name of the data you want"], question: Annotated[str, "the question you want get answer of this data"]):
    """Get content of a document or a repository"""
    # Define the path where the vector store was saved
    load_path = filepath_map[name]

    if load_path.startswith('http'):
        resp = requests.get(load_path)
        resp.raise_for_status()
        return resp.text

    # Load the vector store from the file
    vector_store = InMemoryVectorStore.load(path=load_path, embedding=embeddings)
    retrieved_docs = vector_store.similarity_search(question, k=2)
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\nContent: {doc.page_content}")
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs

@tool("web_page_viewer", description="取得指定 URL 的網頁 HTML 原始內容")
def web_page_viewer(url: str) -> str:
    """
    url: 目標網頁的完整 URL
    回傳值：網頁的原始 HTML 文字
    """
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

issue_comment_api_url = event["issue"]["comments_url"]
pr_comment_api_url = f'{event["issue"]["pull_request"]["url"]}/comments'

def request_json_api(url, headers):
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()

def handle_issue_comments():
    # todo
    pass

def handle_pr_comments():
    # aggregate comment and reply thread
    pr_comments_rows = request_json_api(pr_comment_api_url, GIT_API_HEADERS)
    threads = dict()
    for pr_comments_row in pr_comments_rows:
        if (in_reply_to_id := pr_comments_row.get("in_reply_to_id", None)) is None:
            in_reply_to_id = pr_comments_row["id"]

        threads.setdefault(in_reply_to_id, list())
        threads[in_reply_to_id].append(pr_comments_row)
    
    for cmts in threads.values():
        cmts.sort(key=lambda c: datetime.datetime.strptime(c['created_at'], "%Y-%m-%dT%H:%M:%SZ"))

    return threads

def get_ai_fix_file_content(comment, file):
    prompt = f"""You are a code engineer. You will get the whole file and you need to Modify the file according to the PR comment requirements.
If you're unable to fix the code, you can use get_reference to obtain the necessary information. Supported references include:

youtube_dl: A package used to download files and metadata from YouTube.
sortedcollections: A package that provides a variety of useful container data structures.
codingStyle: A coding style guide document; all contributed code must adhere to it.

Please read the following README to understand this project and the required packages:

README Content:
```
🎬 YouTube Video Download and Classification Project
====================

This is a Python-based project designed to **download YouTube videos and audio and organize them by classification**. The core workflow is roughly as follows:
1. Use **youtube_dl** to download video/audio files and retrieve their metadata  
2. Use **sortedcollections** to build efficient data structures for classification, indexing, and querying  

🚀 Features Overview
-------

* Batch download videos or playlists from YouTube (or other supported platforms)  
* Retrieve metadata such as video title, channel name, duration, and format  
* Organize content into indexed data structures by various categories (e.g., date, channel, tags), supporting fast lookup and sorting  
* Use efficient container management, enabling fast filtering and statistics after classification by various criteria  

🧰 Packages Used
-----------

### **youtube_dl**

* Written in Python, supports Windows, macOS, and Linux, licensed under Unlicense (public domain)  
* Offers extensive CLI options, format selection, batch processing, and multi-platform support  

### **sortedcollections**

* Provides a collection of sorted data structures, including:
    * `ValueSortedDict` (dict sorted by value)  
    * `ItemSortedDict` (dict sorted using a key function)  
    * `NearestDict` (supports nearest key lookup)  
    * `OrderedDict/Set` and `IndexableDict/Set` (access via numeric index)  
    * `SegmentList` (supports fast random insertion and deletion)  
* Implemented purely in Python, no C extensions required, with high performance
```

The following is example that what you get and should return:
file content:
```logging.info('debug log')```

PR comment:
```It should be logging.debug```

Output:
```logging.debug('debug log')```

Now, please check the following file content and the PR comment and then return the modification.

file content:
```{file}```

PR comment:
```{comment}```

Just provide the revised file content directly, without saying anything else."""


    llm = ChatOpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_ENDPOINT_URL"), model="gpt-4o")
    agent = initialize_agent(
        [web_page_viewer, get_reference],
        llm,
        agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        handle_parsing_errors=True,
        verbose=True)
    res = agent(prompt)

    res = res['output']

    return extract_code_blocks(res)


def apply_comment_fix():
    # issue_comments = handle_issue_comments()
    pr_comments = handle_pr_comments()

    threads = pr_comments

    for id, thread in threads.items():
        # read file
        with open(thread[0]['path'], 'r') as f:
            target_file_content = f.read()

        # send to llm
        target_file_content = get_ai_fix_file_content(thread, target_file_content)

        # modify file
        with open(thread[0]['path'], 'w') as f:
            f.write(target_file_content)

        subprocess.run(["git", "add", thread[0]['path']])
        subprocess.run(["git", "commit", "-m", f"Apply change from comment thread {thread[0]['html_url']}"])


if __name__ == '__main__':
    pr_json = request_json_api(event["issue"]["pull_request"]["url"], GIT_API_HEADERS)
    res = subprocess.run(["git", "fetch", "origin", f'bot/{pr_json["head"]["ref"]}'])
    if res.returncode != 0:
        # fix branch not exist
        subprocess.run(["git", "fetch", "origin", f'{pr_json["head"]["ref"]}'])
        subprocess.run(["git", "checkout", f'{pr_json["head"]["ref"]}'])
        subprocess.run(["git", "checkout", "-b", f'bot/{pr_json["head"]["ref"]}'])

    apply_comment_fix()

    subprocess.run(["git", "push", "origin", f'bot/{pr_json["head"]["ref"]}'])
