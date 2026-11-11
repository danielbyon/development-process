# Issue tracker: GitHub

Issues and specs for this repository live in GitHub Issues. Use the `gh` CLI for issue operations.

## Conventions

- Create an issue with `gh issue create --title "..." --body "..."`. Use a heredoc for a multi-line body.
- Read an issue with `gh issue view <number> --json number,title,body,labels,comments`.
- List open issues with `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`. Add label and state filters as needed.
- Make a child issue with `gh issue create --parent <parent> ...`, or link an existing issue with `gh issue edit <parent> --add-sub-issue <child>` (`gh` 2.94+). On older versions, use `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`. If sub-issues are unavailable, start the child body with `Part of #<parent>`.
- Record blockers with GitHub issue dependencies. Use `gh issue create --blocked-by <n>,<n> ...` or `gh issue edit <child> --add-blocked-by <blocker>` (`gh` 2.94+). On older versions, use `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where the blocker's database ID comes from `gh api repos/<owner>/<repo>/issues/<n> --jq .id`. Use the database ID, not the issue number or node ID. If dependencies are unavailable, add `Blocked by: #<n>, #<n>` at the top of the child body. An issue is unblocked when all its blockers are closed.
- Count open blockers with `gh api repos/<owner>/<repo>/issues/<n> --jq .issue_dependencies_summary.blocked_by`. A result of `0` means the issue can start. `gh issue view <n> --json blockedBy` includes closed blockers; filter for open ones with `--jq '[.blockedBy.nodes[] | select(.state == "OPEN")] | length'`.
- Comment with `gh issue comment <number> --body "..."`. Add or remove labels with `gh issue edit <number> --add-label "..."` or `--remove-label "..."`.
- Before closing an issue, post the explanation with `gh issue comment <number> --body "..."`, then run `gh issue close <number>`. On an already closed issue, `gh issue close --comment` drops the comment and still exits 0.

Run `gh repo view --json nameWithOwner` before creating the first issue in a session. Confirm the target if it is not this repository. In a fork, `gh` may default to the upstream project. Do not file issues in `mattpocock/skills` unless the user owns that repository.

## Pull requests in triage

PRs are not part of this repository's triage queue. Keep the "PRs as a request surface" flag set to `no`. Change it to `yes` only if external PRs should be handled as feature requests.

If that flag is changed, use the `gh pr` equivalents to read, list, comment on, label, and close PRs. GitHub uses one number space for issues and PRs, so check `gh pr view 42` first and use `gh issue view 42` if it is not a PR.

## Skill instructions

When a skill says to publish to the issue tracker, create a GitHub issue. When it says to fetch a ticket, use the read command above.

## Wayfinding

The `/wayfinder` skill uses one map issue and child issues as tickets.

- Create the map with the `wayfinder:map` label. It holds the Notes, Decisions-so-far, and Fog sections.
- Create each child as a GitHub sub-issue of the map, with a `wayfinder:<type>` label (`research`, `prototype`, `grilling`, or `task`). If sub-issues are unavailable, add the child to the map's task list and start its body with `Part of #<map>`. Assign the child to the driving developer once claimed.
- Use the blocking commands above for dependencies.
- Find the next ticket by listing the map's open children, then skip any with an open blocker or assignee. The first remaining child in map order is next.
- Claim a ticket with `gh issue edit <n> --add-assignee @me`.
- Resolve it by commenting with the answer, closing it, and adding a context pointer to the map's Decisions-so-far.