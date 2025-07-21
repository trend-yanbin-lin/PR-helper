import os, json, subprocess, logging, requests, datetime
import openai

# 初始化日誌紀錄器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GIT_API_HEADERS = {"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN')}", "Accept": "application/vnd.github+json"}

# 從環境變量讀取 GitHub 事件內容 (issue_comment payload)
with open(os.environ.get('GITHUB_EVENT_PATH'), 'r') as f:
    event = json.load(f)

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
    prompt = f"""Modify the file according to the PR comment requirements.

PR comment:
```{comment}```

file content:
```{file}```

Just provide the revised file content directly, without saying anything else."""

    client = openai.OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_ENDPOINT_URL"),
    )

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    return completion.choices[0].message.content


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
    github-actions[bot]@users.noreply.github.com
    subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"])
    subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"])  
    
    pr_json = request_json_api(event["issue"]["pull_request"]["url"], GIT_API_HEADERS)
    res = subprocess.run(["git", "fetch", "origin", f'bot/{pr_json["head"]["ref"]}'])
    if res.returncode != 0:
        # fix branch not exist
        subprocess.run(["git", "fetch", "origin", f'{pr_json["head"]["ref"]}'])
        subprocess.run(["git", "checkout", f'{pr_json["head"]["ref"]}'])
        subprocess.run(["git", "checkout", "-b", f'bot/{pr_json["head"]["ref"]}'])

    apply_comment_fix()

    subprocess.run(["git", "push", "origin", f'bot/{pr_json["head"]["ref"]}'])
