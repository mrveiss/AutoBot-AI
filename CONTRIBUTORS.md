# Contributing to AutoBot

Thank you for your interest in contributing to AutoBot! Community contributions are what make this project thrive.

---

## 🎯 How to Find Issues to Work On

AutoBot uses GitHub labels to organize issues by skill area and difficulty. Here's how to find work that matches your expertise:

### For First-Time Contributors

Start with **good-first-issue** — these are beginner-friendly and designed as learning opportunities:

- **All good-first-issues:** https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue

### By Skill Area

**Frontend (Vue.js, TypeScript, UI)**
- https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Afrontend+label%3Ahelp-wanted

**Backend (FastAPI, Python, APIs, Database)**
- https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Abackend+label%3Ahelp-wanted

**Infrastructure (Docker, Ansible, DevOps)**
- https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Ainfrastructure+label%3Ahelp-wanted

**Documentation (Guides, Examples, API Docs)**
- https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Adocs+label%3Ahelp-wanted

**Testing (Tests, Coverage, QA)**
- https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Atesting+label%3Ahelp-wanted

### By Priority

**High Priority Issues** (blocking other work, critical bugs)
- https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aissue+is%3Aopen+label%3Apriority-high

---

## 📚 Understanding Difficulty Levels

### `good-first-issue` — Beginner Friendly
- Clear problem statement
- Self-contained (doesn't require changes across multiple files)
- ~1-2 hours to complete
- Minimal architectural knowledge needed
- Great for learning the codebase

### `intermediate` — Moderate Complexity
- Requires understanding one system area
- ~2-8 hours to complete
- Some architectural knowledge needed
- May span multiple files within a system

### `advanced` — High Complexity
- Requires deep architecture knowledge
- Cross-cutting changes or system-wide impact
- ~8+ hours or more
- May require design discussion before implementation

---

## 🛠️ How to Contribute: Step-by-Step

### 1. Find an Issue
Pick an issue from the links above that matches your interests and skill level.

### 2. Comment "I'd Like to Work on This"
Leave a comment on the issue claiming it. This prevents duplicate work.

Example:
> I'd like to work on this. I have experience with Vue.js and would be happy to tackle this frontend issue.

### 3. Set Up Your Development Environment
Follow the [INSTALL.md](INSTALL.md) guide for detailed setup instructions.

Quick setup:
```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
cp .env.example .env
docker compose up -d
```

### 4. Create a Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix-name
```

### 5. Make Your Changes
- Write code following the existing patterns
- Add tests if applicable
- Update documentation if needed

### 6. Submit a Pull Request
Push your branch and open a pull request:
```bash
git push origin feature/your-feature-name
```

Then visit GitHub and create a PR. Include:
- Clear description of what you changed
- Link to the issue you're fixing
- How you tested your changes

### 7. Respond to Review Feedback
A maintainer will review your PR and may request changes. Respond to feedback and keep the conversation going until the PR is merged.

---

## 🤝 Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please see our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.

---

## ❓ Getting Help

### Questions About an Issue?
Leave a comment on the issue — the maintainers and community are here to help.

### General Questions About AutoBot?
Start a discussion: https://github.com/mrveiss/AutoBot-AI/discussions

### Need Help Setting Up?
Check [INSTALL.md](INSTALL.md) or open a discussion with your question.

---

## 📖 Documentation

- **[README.md](README.md)** — Project overview and quick start
- **[INSTALL.md](INSTALL.md)** — Detailed installation guide
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Contribution guidelines
- **[docs/](docs/)** — Full documentation and architecture guides

---

## Thank You!

Your contributions — whether code, docs, bug reports, or ideas — help make AutoBot better for everyone. We appreciate you! 🙏

---

## Next Steps

Ready to contribute?

1. **Pick an issue** from one of the links above
2. **Comment that you're working on it**
3. **Follow the step-by-step guide** above
4. **Submit a PR** with your changes

We're excited to work with you!
