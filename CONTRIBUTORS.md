# Contributing to AutoBot

Thank you for your interest in contributing to AutoBot! This guide will help you find work that matches your skills and understand our contribution process.

---

## Welcome Contributors!

AutoBot is built by and for the community. Whether you're fixing a bug, improving documentation, adding features, or reporting issues—your contributions matter and help make AutoBot better for everyone.

---

## How to Find Issues

Our issues are organized by **skill category** and **difficulty level** to help you find work that matches your expertise.

### For Beginners (New to Open Source)

Start here! These issues are explicitly designed for learning:

- **[Good First Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue)** — Self-contained tasks perfect for your first contribution
  - Expected time: < 2 hours
  - Usually minimal dependencies
  - Great for learning the codebase

### By Skill Category

Pick issues that match your expertise:

#### 🎨 Frontend Developers
**Stack:** Vue.js, TypeScript, CSS, Vite, component development

- **[Frontend Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Afrontend)**
- **[Help Wanted: Frontend](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Afrontend+label%3Ahelp-wanted)**

#### 🔧 Backend Developers
**Stack:** FastAPI, Python, database queries, APIs, async logic

- **[Backend Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Abackend)**
- **[Help Wanted: Backend](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Abackend+label%3Ahelp-wanted)**

#### 🚀 Infrastructure & DevOps
**Stack:** Docker, Ansible, deployment, CI/CD, scaling, networking

- **[Infrastructure Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Ainfrastructure)**
- **[Help Wanted: Infrastructure](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Ainfrastructure+label%3Ahelp-wanted)**

#### 📚 Documentation
**Stack:** Guides, examples, tutorials, README, API docs

- **[Docs Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Adocs)**
- **[Help Wanted: Docs](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Adocs+label%3Ahelp-wanted)**

#### 🧪 Testing & QA
**Stack:** Unit tests, integration tests, test coverage, testing tools

- **[Testing Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Atesting)**
- **[Help Wanted: Testing](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Atesting+label%3Ahelp-wanted)**

### By Priority

If you want to work on what matters most right now:

- **[High Priority Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Apriority-high)** — Critical bugs, blocking work
- **[Medium Priority Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Apriority-medium)** — Important but non-blocking
- **[Low Priority Issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Apriority-low)** — Nice-to-have improvements

---

## Understanding Difficulty Levels

Each issue is labeled by complexity. Here's what each level means:

### 🟢 Good First Issue
- **Scope:** Self-contained, isolated to one component
- **Time:** < 2 hours of focused work
- **Prerequisites:** Understanding of basic concepts in one area
- **Why it's good for beginners:** Limited scope, fewer dependencies, built to teach
- **Example:** Add a missing button to the UI, improve error messages, fix a simple bug

### 🟡 Intermediate
- **Scope:** Requires understanding of one system area
- **Time:** 2-8 hours of work
- **Prerequisites:** Knowledge of at least one major component (e.g., backend APIs, frontend architecture)
- **Why it's good for intermediate contributors:** Not trivial, but not overwhelming
- **Example:** Refactor API endpoints, improve frontend state management, optimize database queries

### 🔴 Advanced
- **Scope:** Cross-cutting concerns, deep architecture knowledge
- **Time:** 8+ hours or requires discussion with maintainers
- **Prerequisites:** Deep knowledge of multiple components or system architecture
- **Why it's challenging:** High impact, complex interactions, may affect multiple systems
- **Example:** Major refactors, new features affecting multiple components, complex performance optimizations

---

## Understanding Skill Categories

AutoBot's codebase spans multiple domains. Pick the area that matches your expertise:

- **Frontend** — User interface, dashboard, chat experience
- **Backend** — API logic, data processing, infrastructure automation
- **Infrastructure** — Docker, Ansible, deployment, CI/CD pipelines
- **Documentation** — Guides, examples, API docs, tutorials
- **Testing** — Unit tests, integration tests, test tooling, QA

---

## Step-by-Step: How to Contribute

### 1️⃣ Find an Issue
Browse the links above to find an issue that matches your skills and interest.

### 2️⃣ Comment on the Issue
Before starting work, comment: **"I'd like to work on this"**

This prevents duplicate work and lets maintainers give you guidance.

### 3️⃣ Set Up Your Development Environment
Follow the instructions in the [README](./README.md) to get AutoBot running locally.

For detailed development setup:
```bash
git clone https://github.com/YOUR_USERNAME/AutoBot-AI.git
cd AutoBot-AI
cp .env.example .env
docker compose up -d
```

See [INSTALL.md](./docs/INSTALL.md) for full setup details.

### 4️⃣ Create a Branch
```bash
git checkout -b feature/your-feature-name
```

Use descriptive branch names:
- `fix/issue-4000-crash-on-startup` (bug fix)
- `feat/command-palette-search` (feature)
- `docs/update-readme-install` (documentation)
- `refactor/simplify-api-layer` (refactoring)

### 5️⃣ Make Your Changes
Edit the code, write tests, update docs if needed.

**Code guidelines:**
- Keep commits focused and descriptive
- Write tests for new features
- Update documentation as needed
- Follow existing code style

### 6️⃣ Submit a Pull Request
Push to your fork and open a PR against `Dev_new_gui` branch.

In your PR description:
- Reference the issue: "Closes #1234"
- Describe what you changed and why
- Mention any limitations or known issues
- Include test results if applicable

Example:
```
Closes #4000

## Description
Fixed crash on startup when knowledge base directory doesn't exist.

## Testing
- [x] Tested with missing directory
- [x] Tested with existing directory
- [x] Ran pytest locally (all pass)
```

### 7️⃣ Respond to Review Feedback
Maintainers will review your work. Questions or requests for changes are normal!

- Address feedback respectfully
- Push new commits to the same branch (PR auto-updates)
- Re-request review once changes are made

### 8️⃣ Celebrate! 🎉
Once approved, your PR will be merged. You're now a contributor to AutoBot!

---

## Code of Conduct

We're committed to fostering an inclusive and respectful community:

- **Be respectful** — Treat all contributors with kindness
- **Be constructive** — Provide thoughtful feedback
- **Be collaborative** — We're all learning and growing together
- **No harassment** — Zero tolerance for discrimination or harassment of any kind
- **Focus on code** — Critique ideas and code, not people

See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) for more details.

---

## Getting Help

Stuck? Have questions? Need guidance?

### 💬 GitHub Discussions
Ask questions, share ideas, and get feedback from the community:
- [GitHub Discussions](https://github.com/mrveiss/AutoBot-AI/discussions)

### 📖 Documentation
- [README](./README.md) — Overview and quick start
- [Installation Guide](./docs/INSTALL.md) — Detailed setup instructions
- [Architecture Docs](./docs/architecture/) — System design and component overview

### 🐛 Issues
If something is broken:
- [Open an issue](https://github.com/mrveiss/AutoBot-AI/issues/new/choose) with details
- Check if someone already reported it (search existing issues first)

---

## Developer Tips

### Running Tests
```bash
# Run all tests
make test

# Run specific test file
pytest autobot-backend/tests/test_chat.py

# Run with coverage
pytest --cov
```

### Building the Project
```bash
# Development mode (live reload)
make dev

# Production build
make build
```

### Code Style
- **Python:** Black + isort (configured in `.pre-commit-config.yaml`)
- **TypeScript/Vue:** ESLint + Prettier (auto-format on save in most IDEs)
- **Commit messages:** Use conventional commits (`feat:`, `fix:`, `docs:`, etc.)

### Pre-commit Hooks
Before committing, pre-commit hooks will automatically format code and run checks:
```bash
# Install pre-commit hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

---

## Getting Recognition

Contributors are recognized in multiple ways:

1. **GitHub profile** — Visible on the repository's contributors page
2. **Commit history** — Your commits are part of AutoBot's permanent record
3. **Community spotlights** — Active contributors may be featured in our discussions/announcements
4. **Maintainer roles** — Significant, consistent contributors may become maintainers

---

## Questions?

- Check [GitHub Discussions](https://github.com/mrveiss/AutoBot-AI/discussions) for common questions
- Open an [issue](https://github.com/mrveiss/AutoBot-AI/issues) if you find a bug
- Comment on an issue if you need clarification

---

## Thank You! 🙏

Whether it's code, documentation, bug reports, or feedback—your contributions make AutoBot better. Thank you for being part of our community!

**Happy contributing!**
