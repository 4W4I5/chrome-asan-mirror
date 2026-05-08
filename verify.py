#!/usr/bin/env python3
"""
Verification script for ASAN Chrome Mirror implementation.
Tests basic functionality of all components.
"""

import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from app.config import Config, get_config, load_config
        from app.database import Database, Build, DownloadStatus
        from app.updater import Updater
        from app.downloader import Downloader
        from app.scheduler import Scheduler
        from app.server import create_app
        from app.main import Application
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_config():
    """Test configuration loading."""
    print("\nTesting configuration...")
    try:
        from app.config import Config
        config = Config()
        assert config.storage_dir is not None
        assert config.min_version >= 0
        assert config.max_version > config.min_version
        assert config.http_port > 0
        print(f"✓ Config loaded successfully:")
        print(f"  - Storage: {config.storage_dir}")
        print(f"  - Version range: {config.min_version}-{config.max_version}")
        print(f"  - HTTP: {config.http_host}:{config.http_port}")
        return True
    except Exception as e:
        print(f"✗ Config test failed: {e}")
        return False


def test_database():
    """Test database initialization."""
    print("\nTesting database...")
    try:
        from app.database import Database, Build, DownloadStatus
        from pathlib import Path
        import tempfile
        
        # Create temp database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            
            # Test insert and retrieve
            build = Build(
                version="120.0.0.0",
                os="win64",
                filepath=Path("/tmp/120.0.0.0.zip"),
                status=DownloadStatus.SUCCESS,
                checksum="abc123"
            )
            db.insert_build(build)
            
            # Retrieve
            retrieved = db.get_build("120.0.0.0", "win64")
            assert retrieved is not None
            assert retrieved.version == "120.0.0.0"
            
            # List
            builds = db.list_downloads()
            assert len(builds) > 0
            
            # Stats
            stats = db.get_stats()
            assert stats['total_downloads'] >= 0
            
            print(f"✓ Database working correctly:")
            print(f"  - Schema created")
            print(f"  - Insert/retrieve working")
            print(f"  - Queries working")
            return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fastapi_app():
    """Test FastAPI application creation."""
    print("\nTesting FastAPI app...")
    try:
        from app.server import create_app
        from app.config import Config
        from app.database import Database
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))
            db = Database(Path(tmpdir) / "test.db")
            app = create_app(config, db)
            
            # Check routes exist
            routes = [route.path for route in app.routes]
            required_routes = ["/", "/health", "/metrics", "/win64/", "/linux/"]
            for route in required_routes:
                if route not in routes:
                    print(f"✗ Missing route: {route}")
                    return False
            
            print(f"✓ FastAPI app created successfully:")
            print(f"  - Routes: {', '.join(required_routes)}")
            return True
    except Exception as e:
        print(f"✗ FastAPI test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_structure():
    """Test that all required files exist."""
    print("\nTesting file structure...")
    required_files = [
        "app/__init__.py",
        "app/config.py",
        "app/database.py",
        "app/updater.py",
        "app/downloader.py",
        "app/scheduler.py",
        "app/server.py",
        "app/main.py",
        "requirements.txt",
        "config.yaml.example",
        "install.sh",
        "systemd/asan-chrome-mirror.service",
        "README.md",
        ".gitignore"
    ]
    
    project_dir = Path(__file__).parent
    missing_files = []
    
    for file in required_files:
        file_path = project_dir / file
        if not file_path.exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"✗ Missing files: {', '.join(missing_files)}")
        return False
    
    print(f"✓ All required files present:")
    for file in required_files:
        print(f"  ✓ {file}")
    
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("ASAN Chrome Mirror - Verification Tests")
    print("=" * 60)
    
    tests = [
        test_file_structure,
        test_imports,
        test_config,
        test_database,
        test_fastapi_app,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("✓ All verification tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
