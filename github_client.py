"""Thin wrapper around PyGithub for the issue-crew target repo."""
import os

from dotenv import load_dotenv
from github import Auth, Github

load_dotenv()

REPO_NAME = os.environ.get("TARGET_REPO", "Gourish-Pednekar/sample-target-app")


def _repo():
    gh = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))
    return gh.get_repo(REPO_NAME)


def get_issue(number: int) -> dict:
    issue = _repo().get_issue(number)
    if issue.pull_request is not None:
        raise ValueError(f"#{number} is a pull request, not an issue")
    return {
        "number": issue.number,
        "title": issue.title,
        "body": issue.body or "",
        "url": issue.html_url,
    }


def list_open_issues() -> list[dict]:
    return [
        {"number": i.number, "title": i.title}
        for i in _repo().get_issues(state="open")
        if i.pull_request is None
    ]


def create_pull_request(title: str, body: str, head: str, base: str = "main") -> str:
    pr = _repo().create_pull(title=title, body=body, head=head, base=base)
    return pr.html_url



def comment_on_issue(number: int, body: str) -> str:
    comment = _repo().get_issue(number).create_comment(body)
    return comment.html_url