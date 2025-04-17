# TODO and FIXME Comment Guidelines

This document describes the conventions for using TODO and FIXME comments in the hikarie_bot project.

## Format

- Use `# TODO:` for tasks or improvements to be addressed later.
- Use `# FIXME:` for known bugs or technical debt that should be fixed.
- Optionally, include your GitHub username and/or an issue number for traceability.

### Examples

```python
# TODO: Refactor this function for better readability
# TODO(@username): Add support for new Slack event type
# TODO(#42): Remove hardcoded values

# FIXME: Handle edge case when input is None
# FIXME(@username): Fix race condition in async handler
```

## Best Practices

- Be specific about what needs to be done or fixed.
- Link to a GitHub issue if one exists.
- Review TODO and FIXME comments regularly and address them as part of ongoing development.
- Remove comments once the task or fix is complete.

## Review Process

- During code review, reviewers should check for outdated or unclear TODO/FIXME comments.
- Consider creating a GitHub issue for any significant TODO/FIXME that is not already tracked.
