# Contributing to Hospital AI Assistant

Thank you for your interest in contributing to Hospital AI Assistant! We welcome contributions from the community.

## 🎯 How to Contribute

### Reporting Bugs
1. Check existing [issues](https://github.com/shashankpasikanti91-blip/Hospital-AI-Assistant/issues)
2. Create detailed bug report with:
   - Description of the issue
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment (Python version, OS, etc.)

### Suggesting Features
1. Use [GitHub Discussions](https://github.com/shashankpasikanti91-blip/Hospital-AI-Assistant/discussions)
2. Describe the feature and use case
3. Wait for community feedback before implementing

### Code Contributions

#### Step 1: Fork & Clone
```bash
git clone https://github.com/your-username/Hospital-AI-Assistant.git
cd Hospital-AI-Assistant
```

#### Step 2: Create Feature Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b bugfix/bug-description
```

#### Step 3: Make Changes
- Follow code style guidelines
- Add tests for new features
- Update documentation

#### Step 4: Commit
```bash
git commit -m "feat: add new feature" 
# or
git commit -m "fix: resolve issue #123"
```

#### Step 5: Push & Create Pull Request
```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub with:
- Clear title and description
- Link to related issues
- Screenshots (if UI changes)

## 📋 Development Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy environment template
cp .env.example .env
# Add your API keys

# 4. Run tests
python -m pytest

# 5. Start development server
python hospital_server_final.py
```

## ✅ Code Guidelines

- Follow PEP 8 style guide
- Add docstrings to functions
- Write meaningful commit messages
- Keep functions small and focused
- Add type hints where possible

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_chatbot.py

# Run with coverage
pytest --cov=src tests/
```

## 📝 Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types:** feat, fix, docs, style, refactor, perf, test, chore
**Subject:** Short, imperative description (max 50 chars)
**Body:** Detailed explanation (optional)
**Footer:** Reference issues, breaking changes (optional)

**Example:**
```
feat: add multilingual support for French

- Add French language configuration
- Implement French voice recognition
- Update UI translations

Closes #42
```

## 🤝 Code Review Process

1. Submit your Pull Request
2. Author reviews code
3. Automated tests run
4. Community provides feedback
5. Make requested changes
6. PR is merged

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 🙏 Code of Conduct

- Be respectful and inclusive
- No harassment or discrimination
- Welcome feedback and criticism
- Focus on ideas, not individuals

## Questions?

- 📖 Check [documentation](README.md)
- 💬 Start a [discussion](https://github.com/shashankpasikanti91-blip/Hospital-AI-Assistant/discussions)
- 🐛 Open an [issue](https://github.com/shashankpasikanti91-blip/Hospital-AI-Assistant/issues)

---

**Thank you for contributing! 🎉**
