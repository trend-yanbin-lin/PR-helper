import os, json, re, subprocess, logging
import openai

# 初始化日誌紀錄器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 從環境變量讀取 GitHub 事件內容 (issue_comment payload)
event_path = os.environ.get('GITHUB_EVENT_PATH')
with open(event_path, 'r') as f:
    event = json.load(f)
logger.info(f"Worker get event\n{event}")
comment_body = event["comment"]["body"]
issue_number = event["issue"]["number"]            # 對應的 Issue/PR 編號
comment_id = event["comment"]["id"]                # 評論ID，可用於唯一標識這次修改
is_pr = True if event["issue"].get("pull_request") else False
pr_branch = None
if is_pr:
    # 從事件中提取 PR 分支名稱 (若payload未直接給出，需要先前Checkout步驟已經切換到PR分支)
    pr_branch = subprocess.check_output(["git", "branch", "--show-current"]).decode().strip()
    logger.info(f"Working on PR #{issue_number}, branch: {pr_branch}")
else:
    logger.info(f"Working on Issue #{issue_number} (no existing PR, will create new PR branch)")

# 判斷評論指令類型
command = comment_body.strip().split()[0]  # 取第一個詞辨別是「添加修改/重新修改/刪除修改」
logger.info(f"Detected command: {command}")

try:
    if command == "添加修改":
        # 1. 添加修改：應用新代碼修改
        # 檢查評論中是否包含程式碼區塊 (Markdown 三引號標記)
        code_block_match = re.search(r"```(.*?[\r\n]+)([\s\S]*?)```", comment_body)
        if code_block_match:
            # 提取提供的新代碼片段
            new_code = code_block_match.group(2)
            # 嘗試從評論文字中找出目標檔案路徑或函式名稱 (假設評論中有提及)
            target_file = None
            file_match = re.search(r'文件[：:]\s*([\w/\.-]+\.[a-zA-Z]+)', comment_body)
            if file_match:
                target_file = file_match.group(1)
            # 如果有指定檔案，將代碼寫入該檔案；否則嘗試從代碼片段推出檔案 (此處簡化處理)
            if target_file:
                logger.info(f"Applying provided code changes to file: {target_file}")
                with open(target_file, 'w', encoding='utf-8') as f:
                    f.write(new_code)
            else:
                # 簡化情況：假設代碼片段即為需要替換的整個檔案內容，此時不妨要求評論務必提供檔名
                raise Exception("未能識別目標檔案，無法應用代碼片段")
        else:
            # 若評論沒有直接的代碼，使用 GPT 根據描述生成修改後的代碼
            # 透過解析評論內容找出相關的檔案或函式線索
            target_file = None
            file_match = re.search(r'修改\s*([\w/\.-]+\.[a-zA-Z]+)', comment_body)
            if file_match:
                target_file = file_match.group(1)
            if not target_file:
                raise Exception("評論未指定修改目標，且未提供程式碼片段")
            # 讀取目標檔案內容以擷取需要修改的片段作為上下文
            with open(target_file, 'r', encoding='utf-8') as f:
                original_code = f.read()
            prompt = (f"以下是一個程式檔案的內容以及一項修改請求，"
                      f"請根據請求修改代碼。\n\n<原始代碼>:\n{original_code}\n"
                      f"<修改請求>:\n{comment_body}\n"
                      f"請提供修改後的完整代碼。")
            openai.api_key = os.getenv("OPENAI_API_KEY")
            logger.info("Calling OpenAI GPT API to generate code changes...")
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            # 提取GPT回覆中的代碼內容
            new_code = response['choices'][0]['message']['content']
            # 將 GPT 生成的新代碼寫回目標檔案
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(new_code)
            logger.info(f"GPT 修改建議已應用至 {target_file}")
        # 執行 Git 提交
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"])
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])
        commit_msg = f"Apply suggested changes (Case #{issue_number}, comment {comment_id})"
        subprocess.run(["git", "add", "-A"])
        subprocess.run(["git", "commit", "-m", commit_msg])
        logger.info(f"Committed changes: {commit_msg}")
        if is_pr:
            # 若已有對應 PR，直接推送到該 PR 分支
            subprocess.run(["git", "push"])  # 使用 persist-credentials 所提供的權限推送
            logger.info(f"Pushed commit to existing PR #{issue_number} branch.")
        else:
            # 尚無 PR：創建新分支並推送，然後透過 GitHub API 建立 PR
            new_branch = f"auto-mod-{issue_number}-{comment_id}"
            subprocess.run(["git", "branch", "-M", new_branch])  # 重命名當前分支為新分支
            subprocess.run(["git", "push", "-u", "origin", new_branch])
            logger.info(f"Pushed new branch '{new_branch}', creating Pull Request...")
            import requests
            repo = event["repository"]["full_name"]  # e.g. owner/repo
            api_url = f"https://api.github.com/repos/{repo}/pulls"
            pr_title = f"Auto Mod for Issue #{issue_number}"
            pr_body = f"自動產生的修改，來源Issue #{issue_number} 的評論 {comment_id}。"
            headers = {"Authorization": f"token {os.environ['GITHUB_TOKEN']}"}
            payload = {
                "title": pr_title,
                "head": new_branch,
                "base": event["repository"]["default_branch"],  # 對應目標分支（例如 main）
                "body": pr_body,
                "issue": issue_number  # 關聯 issue，可選
            }
            resp = requests.post(api_url, json=payload, headers=headers)
            if resp.status_code >= 300:
                raise Exception(f"PR creation failed: {resp.text}")
            logger.info(f"Pull Request created for Issue #{issue_number}: {resp.json().get('html_url')}")

    elif command == "重新修改":
        # 2. 重新修改：修正之前的提交
        # 找到之前「添加修改」所生成的 commit，可透過 commit 訊息中的 comment ID 尋找
        target_commit = None
        log = subprocess.check_output(["git", "log", "--pretty=format:%H %s"]).decode()
        for line in log.splitlines():
            if str(comment_id) in line:
                target_commit = line.split()[0]
                break
        if not target_commit:
            raise Exception("找不到需要重新修改的對應 commit")
        logger.info(f"Found target commit {target_commit} to modify.")
        # 獲取該 commit 修改的檔案和內容差異
        diff_text = subprocess.check_output(["git", "diff", f"{target_commit}^!", "--unified=0"]).decode()
        # 使用 GPT 幫助根據評論對差異進行修改
        prompt = (f"下面是一段補丁(diff)，它將原始代碼改成現在的代碼。\n"
                  f"補丁內容：\n{diff_text}\n\n"
                  f"評論提出了新的修改要求：{comment_body}\n"
                  f"請據此補丁和要求，提供修正後的程式碼變更（只需給出更新後的完整代碼片段）。")
        openai.api_key = os.getenv("OPENAI_API_KEY")
        logger.info("Calling OpenAI GPT API for redo modification...")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        new_diff = response['choices'][0]['message']['content']
        # 將 GPT 產生的新的差異應用到代碼。
        # 簡化處理：假設 GPT 回傳的是統一 diff 格式，可以嘗試直接應用。
        patch_file = "patch.diff"
        with open(patch_file, 'w') as pf:
            pf.write(new_diff)
        # 使用 git apply 套用補丁
        result = subprocess.run(["git", "apply", patch_file])
        if result.returncode != 0:
            raise Exception("自動補丁應用失敗，需要人工處理衝突")
        # 提交修正後的更改
        fix_commit_msg = f"Refine changes (Case #{issue_number}, comment {comment_id})"
        subprocess.run(["git", "add", "-A"])
        subprocess.run(["git", "commit", "-m", fix_commit_msg])
        subprocess.run(["git", "push"])
        logger.info(f"Pushed a refined commit: {fix_commit_msg}")

    elif command == "刪除修改":
        # 3. 刪除修改：撤銷之前的修改提交
        # 同樣根據唯一 ID 找到目標 commit
        target_commit = None
        log = subprocess.check_output(["git", "log", "--pretty=format:%H %s"]).decode()
        for line in log.splitlines():
            if str(comment_id) in line:
                target_commit = line.split()[0]
                break
        if not target_commit:
            raise Exception("找不到需要刪除的對應 commit")
        logger.info(f"Reverting commit {target_commit} from branch...")
        # 檢查該 commit 是否為 HEAD
        head_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        if target_commit.startswith(head_commit):
            # 若是最新提交，使用 reset 移除並強制推送
            subprocess.run(["git", "reset", "--hard", f"{head_commit}^"])
            subprocess.run(["git", "push", "--force"])
            logger.info(f"Commit {target_commit} removed via reset and force-pushed.")
        else:
            # 若非末端提交，使用 git revert 產生還原 commit
            revert_msg = f"Revert commit {target_commit[:7]} (Case #{issue_number})"
            subprocess.run(["git", "revert", "--no-edit", target_commit])
            subprocess.run(["git", "commit", "--amend", "-m", revert_msg])  # 修改默認訊息以包含Case ID
            subprocess.run(["git", "push"])
            logger.info(f"Created revert commit for {target_commit} and pushed.")
    else:
        logger.info("無定義的指令，跳過處理。")

except Exception as e:
    # 錯誤處理：將錯誤記錄在日誌，必要時可以透過 GitHub API 發送評論提示失敗
    logger.error(f"自動修改工具執行失敗: {e}")
    # 可以選擇將錯誤回覆至 PR 評論，以通知使用者 (此處為可選步驟)
    # 如：
    # requests.post(f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
    #              json={"body": f"⚠️ 自動修改失敗: {e}"}, headers=headers)
    raise
