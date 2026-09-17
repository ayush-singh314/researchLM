from backend.api.app import create_app

app = create_app()


def main():
    import uvicorn

    # Watch only app code. Default --reload watches cwd, including .venv;
    # Windows then reloads forever when site-packages files are touched.
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["backend"],
        reload_excludes=[".venv", ".git", "frontend"],
    )


if __name__ == "__main__":
    main()
