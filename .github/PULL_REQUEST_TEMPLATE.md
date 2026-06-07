## Summary

<!-- Describe what this PR does and why. Link any related issues (e.g. "Closes #123"). -->

## Type of change

<!-- Check all that apply. -->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing behavior to change)
- [ ] Refactor / internal cleanup (no behavior change)
- [ ] Documentation update
- [ ] Infrastructure / Terraform change
- [ ] CI / tooling change

## Checklist

### Code quality
- [ ] `ruff check` passes with zero errors (`python3 -m ruff check src/ tests/` in the affected module)
- [ ] `mypy` type-check passes (or pre-existing drift is unchanged — do not introduce new mypy errors)
- [ ] `pytest` test suite passes locally or CI green on this branch

### Domain hygiene
- [ ] `scripts/domain-scan.sh` returns zero HARD-term hits (run from repo root)
- [ ] No domain-specific logic, identifiers, or data models are present in platform code (see CLAUDE.md §"Zero Domain Contamination")

### Security
- [ ] No secrets, API keys, tokens, AWS account IDs, or internal hostnames are present in any tracked file
- [ ] No new hardcoded defaults for model names, regions, sampling rates, or deployment-varying values — all sourced from blueprints / env / config

### Documentation
- [ ] Docstrings updated for any public API changes
- [ ] Relevant `docs/` pages or `operator/` documents updated if behavior changed
- [ ] `NOTICE` updated if a new third-party dependency is introduced (Apache-2.0 requirement)

### Infrastructure (Terraform changes only)
- [ ] `terraform plan` in a domain consumer repo (e.g. `your-domain-repo/infra`) produces no unexpected destroy actions
- [ ] All three `tfvars` files (`dev`, `staging`, `production`) updated if new variables are added
- [ ] Sub-module interface changes propagate to all consumers

### Commit discipline
- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `ci:`, `test:`)
- [ ] Each commit is a single logical change

## Testing notes

<!-- Describe how you tested this change. For platform changes, include the CI run link or Step Functions execution ID if applicable. -->

## Additional context

<!-- Any other information reviewers should know. Screenshots, diagrams, links to design docs, etc. -->
