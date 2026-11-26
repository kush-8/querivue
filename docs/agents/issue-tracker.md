# Issue Tracker Configuration

**Tracker:** GitHub Issues

**Repo URL:** https://github.com/kush-8/querivue

**CLI tools:** Uses `gh` CLI for issue operations.

**Workflow:**
- Issues are tracked in the GitHub repository
- PRs are developed in feature branches and opened as PRs
- Code review happens via GitHub PR reviews
- Merged PRs close associated issues via commit messages or PR descriptions

**Setup verified:**
```bash
gh repo view
```