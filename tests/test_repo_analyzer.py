import json
import tempfile
from pathlib import Path
import pytest

from src.analyzer.repo_analyzer import (
    RepoAnalyzer,
    Evidence,
    Language,
    Framework,
    Module,
    Feature,
    Dependency,
)


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test-repo"
        repo_path.mkdir()
        yield repo_path


@pytest.fixture
def analyzer_with_repo(temp_repo):
    analyzer = RepoAnalyzer("https://github.com/test/repo")
    analyzer.repo_path = temp_repo
    analyzer.commit_sha = "abc123"
    return analyzer


class TestLanguageDetection:
    def test_detect_python_files(self, analyzer_with_repo, temp_repo):
        (temp_repo / "main.py").write_text("print('hello')")
        (temp_repo / "utils.py").write_text("def foo(): pass")

        languages = analyzer_with_repo.detect_languages()

        assert len(languages) == 1
        assert languages[0].name == "Python"
        assert languages[0].ratio == 1.0

    def test_detect_multiple_languages(self, analyzer_with_repo, temp_repo):
        (temp_repo / "main.py").write_text("print('hello')")
        (temp_repo / "app.ts").write_text("const x = 1")
        (temp_repo / "index.js").write_text("console.log('hi')")

        languages = analyzer_with_repo.detect_languages()

        assert len(languages) == 3
        lang_names = {l.name for l in languages}
        assert lang_names == {"Python", "TypeScript", "JavaScript"}

    def test_skip_node_modules(self, analyzer_with_repo, temp_repo):
        (temp_repo / "main.py").write_text("print('hello')")
        node_modules = temp_repo / "node_modules"
        node_modules.mkdir()
        (node_modules / "dep.js").write_text("const x = 1")

        languages = analyzer_with_repo.detect_languages()

        assert len(languages) == 1
        assert languages[0].name == "Python"


class TestFrameworkDetection:
    def test_detect_python_frameworks_from_requirements(self, analyzer_with_repo, temp_repo):
        requirements = temp_repo / "requirements.txt"
        requirements.write_text("fastapi==0.100.0\nuvicorn\npydantic")

        frameworks = analyzer_with_repo.detect_frameworks()

        fw_names = {fw.name for fw in frameworks}
        assert "FastAPI" in fw_names
        assert "Uvicorn" in fw_names
        assert "Pydantic" in fw_names

    def test_detect_js_frameworks_from_package_json(self, analyzer_with_repo, temp_repo):
        package_json = temp_repo / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {
                "react": "^18.0.0",
                "redux": "^4.0.0"
            },
            "devDependencies": {
                "tailwindcss": "^3.0.0"
            }
        }))

        frameworks = analyzer_with_repo.detect_frameworks()

        fw_names = {fw.name for fw in frameworks}
        assert "React" in fw_names
        assert "Redux" in fw_names
        assert "TailwindCSS" in fw_names

    def test_detect_nested_requirements(self, analyzer_with_repo, temp_repo):
        backend = temp_repo / "backend"
        backend.mkdir()
        requirements = backend / "requirements.txt"
        requirements.write_text("django==4.0\ncelery")

        frameworks = analyzer_with_repo.detect_frameworks()

        fw_names = {fw.name for fw in frameworks}
        assert "Django" in fw_names
        assert "Celery" in fw_names


class TestArchitectureDetection:
    def test_detect_client_server(self, analyzer_with_repo, temp_repo):
        (temp_repo / "frontend").mkdir()
        (temp_repo / "backend").mkdir()

        arch = analyzer_with_repo.detect_architecture_type()

        assert arch["type"] == "client-server"
        assert "frontend" in arch["layers"]
        assert "backend" in arch["layers"]

    def test_detect_web_from_frameworks(self, analyzer_with_repo, temp_repo):
        requirements = temp_repo / "requirements.txt"
        requirements.write_text("fastapi==0.100.0")

        arch = analyzer_with_repo.detect_architecture_type()

        assert arch["type"] in ("api", "web")
        assert "backend" in arch["layers"]

    def test_detect_library(self, analyzer_with_repo, temp_repo):
        pyproject = temp_repo / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "my-library"
version = "1.0.0"
""")

        arch = analyzer_with_repo.detect_architecture_type()

        assert arch["type"] == "library"


class TestDependencyParsing:
    def test_parse_requirements_with_versions(self, analyzer_with_repo, temp_repo):
        requirements = temp_repo / "requirements.txt"
        requirements.write_text("""
fastapi==0.100.0
uvicorn>=0.20.0
pydantic~=2.0
requests
# comment
-r other.txt
""")

        deps = analyzer_with_repo.detect_dependencies()

        dep_dict = {d.name: d.version for d in deps}
        assert dep_dict["fastapi"] == "==0.100.0"
        assert dep_dict["uvicorn"] == ">=0.20.0"
        assert dep_dict["pydantic"] == "~=2.0"
        assert dep_dict["requests"] == "*"

    def test_parse_package_json_dependencies(self, analyzer_with_repo, temp_repo):
        package_json = temp_repo / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {
                "vue": "^3.0.0"
            },
            "devDependencies": {
                "typescript": "~5.0.0"
            }
        }))

        deps = analyzer_with_repo.detect_dependencies()

        dep_dict = {d.name: d.version for d in deps}
        assert dep_dict["vue"] == "^3.0.0"
        assert dep_dict["typescript"] == "~5.0.0"


class TestFeatureExtraction:
    def test_extract_fastapi_routes(self, analyzer_with_repo, temp_repo):
        main_py = temp_repo / "main.py"
        main_py.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello"}

@app.post("/users")
def create_user():
    pass

@router.get("/items/{item_id}")
def get_item(item_id: int):
    pass
""")

        features = analyzer_with_repo.extract_features()

        routes = {f.summary for f in features}
        assert "Endpoint: /" in routes
        assert "Endpoint: /users" in routes
        assert "Endpoint: /items/{item_id}" in routes

    def test_extract_express_routes(self, analyzer_with_repo, temp_repo):
        server_js = temp_repo / "server.js"
        server_js.write_text("""
const express = require('express');
const app = express();

app.get('/api/health', (req, res) => {
    res.json({ status: 'ok' });
});

router.post('/api/users', async (req, res) => {
    // create user
});
""")

        features = analyzer_with_repo.extract_features()

        routes = {f.summary for f in features}
        assert "Endpoint: /api/health" in routes
        assert "Endpoint: /api/users" in routes


class TestModuleExtraction:
    def test_extract_modules_with_roles(self, analyzer_with_repo, temp_repo):
        (temp_repo / "auth").mkdir()
        (temp_repo / "users").mkdir()
        (temp_repo / "utils").mkdir()

        modules = analyzer_with_repo.extract_modules()

        module_dict = {m.name: m.role for m in modules}
        assert module_dict["auth"] == "authentication"
        assert module_dict["users"] == "user-management"
        assert module_dict["utils"] == "utilities"

    def test_skip_system_directories(self, analyzer_with_repo, temp_repo):
        (temp_repo / "app").mkdir()
        (temp_repo / "node_modules").mkdir()
        (temp_repo / "__pycache__").mkdir()
        (temp_repo / ".git").mkdir()

        modules = analyzer_with_repo.extract_modules()

        module_names = {m.name for m in modules}
        assert "app" in module_names
        assert "node_modules" not in module_names
        assert "__pycache__" not in module_names
        assert ".git" not in module_names


class TestBuildFilesAndEntrypoints:
    def test_find_build_files(self, analyzer_with_repo, temp_repo):
        (temp_repo / "Dockerfile").write_text("FROM python:3.11")
        (temp_repo / "docker-compose.yml").write_text("version: '3'")
        (temp_repo / "pyproject.toml").write_text("[project]")

        build_files = analyzer_with_repo._find_build_files()

        assert "Dockerfile" in build_files
        assert "docker-compose.yml" in build_files
        assert "pyproject.toml" in build_files

    def test_find_nested_build_files(self, analyzer_with_repo, temp_repo):
        frontend = temp_repo / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text("{}")
        (frontend / "vite.config.ts").write_text("export default {}")

        build_files = analyzer_with_repo._find_build_files()

        assert any("package.json" in f for f in build_files)
        assert any("vite.config.ts" in f for f in build_files)

    def test_find_entrypoints(self, analyzer_with_repo, temp_repo):
        (temp_repo / "main.py").write_text("if __name__ == '__main__': pass")
        backend = temp_repo / "backend" / "app"
        backend.mkdir(parents=True)
        (backend / "main.py").write_text("app = FastAPI()")

        entrypoints = analyzer_with_repo._find_entrypoints()

        assert "main.py" in entrypoints
        assert any("backend" in e and "main.py" in e for e in entrypoints)


class TestFactsJsonGeneration:
    def test_generate_complete_facts(self, analyzer_with_repo, temp_repo):
        (temp_repo / "main.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {}
""")
        (temp_repo / "requirements.txt").write_text("fastapi==0.100.0")

        facts = analyzer_with_repo.generate_facts_json()

        assert facts["schema"] == "facts.v1"
        assert facts["repo"]["url"] == "https://github.com/test/repo"
        assert facts["repo"]["commit"] == "abc123"
        assert len(facts["languages"]) > 0
        assert len(facts["frameworks"]) > 0
        assert len(facts["features"]) > 0
        assert len(facts["runtime"]["dependencies"]) > 0
