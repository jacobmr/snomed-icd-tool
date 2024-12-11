import os
import subprocess

def git_autosync():
    try:
        # Change to your project directory
        project_dir = "/home/jacobr/vsac"
        os.chdir(project_dir)

        # Stage all changes
        subprocess.run(["git", "add", "."], check=True)

        # Commit changes with a generic message
        subprocess.run(["git", "commit", "-m", "Auto-sync changes"], check=True)

        # Push changes to GitHub
        subprocess.run(["git", "push", "origin", "main"], check=True)

        print("Changes synced successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error during Git sync: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    git_autosync()