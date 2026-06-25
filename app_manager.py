# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

"""This script will set the DIY Studio App either to a specific tag
(CHECKOUT_TAG), or, when branch is set to 'main', it will read the local
app_version.txt and if any remote tags are found with a higher patch
level, it will checkout to that tag as an auto-update mechanism.

For example: it will update 1.0.0 to 1.0.1, but not
to 1.1.0 or 2.0.0. It will use 'git checkout' command for this.

If a branch other than 'main' is specified, it will simply switch to,
or pull, the latest commit in that branch.

Once the local repository has been set to the intended state, the
DIY Studio App will be started. When the user exits this app with a
shutdown request, this script will shut down the computer.

This script should be copied to a location outside of this repository
in order to work correctly.

By default, local changes are preserved and updates are skipped when
the repository has local changes. Set ALLOW_DESTRUCTIVE_RESET = True on
a deployed studio machine to enable auto-repair + auto-update behavior.

app_version.txt should contain the following key-value lines:
version=x.x.x
branch=name of branch

For all branches other than main, version will be irrelevant
"""

import logging
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime

ALLOW_DESTRUCTIVE_RESET = False
APP_VERSION_FILE = "app_version.txt"
BRANCH = "main" # "main" | "develop" | "release-v1.x"
CHECKOUT_TAG = None # if not None it will checkout to this specific tag
LOGS_DIR: str = os.path.join(os.getcwd(), "logs")
MAX_RETRY_ATTEMPTS = 3
REPOSITORY_PATH = "C:/Software/diy-studio-app/"

# Stable tags: v1.2.3 or 1.2.3
SEMVER_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

logger = logging.getLogger(__name__)

def get_current_branch():
    """Return a boolean for success/failure + the current git branch"""
    return retrieve_git_info("rev-parse", "--abbrev-ref", "HEAD")

def get_current_branch_from_local_tag(local_tag):
    """Determine the current branch from the tag in app_version.txt.

    This function only exists for legacy app_version.txt layouts.
    Branch name should be explicitly specified on the second
    line of app_version.txt - in which case this function
    will not be called."""
    if local_tag[0:3] == "dev":
        return "development"
    elif local_tag[0:7] == "testing":
        return "testing"
    elif local_tag[0:7] == "release":
        return local_tag
    elif SEMVER_TAG_RE.match(local_tag):
        return "main"
    else:
        # In case nothing matches, the entire tag
        # should be taken as branch name
        return local_tag

def perform_git_action(*args) -> bool:
    """Use subprocess.run to perform a git action and return True/False"""
    if not args or not args[0]:
        logger.error("Error: perform_git_action: no Git action specified")
        return False
    try:
        logger.info(f"Trying to perform Git action: {args}")
        result = subprocess.run(
            ["git", *args],
            text=True,
            capture_output=True,
            check=True
            )
        if result.stderr:
            logger.info("Git output: %s", result.stderr.strip())
    except subprocess.CalledProcessError as e:
        logger.error("Git command failed: %s", " ".join(["git", *args]))
        if e.stdout:
            logger.error("Git stdout: %s", e.stdout.strip())
        if e.stderr:
            logger.error("Git stderr: %s", e.stderr.strip())
        return False
    return True

def parse_app_info(file_content: str):
    """Return version and branch from app_version.txt content."""
    app_info = {}
    lines = file_content.splitlines()

    if len(lines) == 1 and "=" not in lines[0]:
        version = lines[0].strip()
        return version, get_current_branch_from_local_tag(version)

    for line in lines:
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        key, separator, value = line.partition("=")

        if not separator:
            continue

        app_info[key.strip().lower()] = value.strip()

    version = app_info.get("version")
    branch = app_info.get("branch")

    if version and not branch:
        branch = get_current_branch_from_local_tag(version)

    return version, branch

def parse_stable_version(tag: str):
    """Return [major, minor, patch] for stable tags, otherwise None."""
    if not tag:
        return None

    match = SEMVER_TAG_RE.fullmatch(tag.strip())

    if not match:
        return None

    return [int(part) for part in match.groups()]

def retrieve_git_info(*args):
    """Use subprocess.run to perform a git action and return the output"""
    if not args or not args[0]:
        logger.error("Error: retrieve_git_info: no Git action specified")
        return False, None

    try:
        logger.info(f"Trying to retrieve Git info: {args}")
        result = subprocess.run(
            ["git", *args],
            text=True,
            capture_output=True,
            check=True
        )
        if result.stderr:
            logger.info("Git output: %s", result.stderr.strip())
        else:
            stdout = result.stdout.strip()
            logger.info(
                "Retrieved Git info: %s", ", ".join(stdout.splitlines())
            )

    except subprocess.CalledProcessError as e:
        logger.error("Git command failed: %s", " ".join(["git", "rev-parse"]))
        if e.stdout:
            logger.error("Git stdout: %s", e.stdout.strip())
        if e.stderr:
            logger.error("Git stderr: %s", e.stderr.strip())
        return False, None

    return True, result.stdout.strip()

def get_local_changes():
    """Return success/failure and the output of git status --porcelain."""
    return retrieve_git_info("status", "--porcelain")

def run_app(repo_path: str, crashed=False, retry_attempts: int = 0) -> None:
    """Run the application"""
    cmd = [sys.executable, "app.py"]

    if crashed:
        cmd.append("--restart")

    logger.info("Starting application %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            check=False
        )
    except OSError as exc:
        logger.error("Failed to start application: %s", exc)
        return

    if result.returncode == 0:
        logger.info("Application exited normally with shutdown request")
        shutdown(0)
        return
    elif result.returncode == 100:
        logger.info("Application exited normally with reboot request")
        shutdown(100)
        return
    else:
        logger.error(
            "Application exited with code %s.",
            result.returncode,
        )
        # Restart the app with command line argument to show error
        # message on startup
        if retry_attempts < MAX_RETRY_ATTEMPTS:
            r = retry_attempts + 1
            time.sleep(5)
            logger.info("Restarting app, attempt %s", r)
            run_app(REPOSITORY_PATH, crashed=True, retry_attempts=r)

def split_version(tag: str):
    """Split stable version string ('1.0.0') into a list where
    list[0] contains the major version number,
    list[1] contains the minor version number,
    list[2] contains the patch version number"""
    version = parse_stable_version(tag)

    if version is None:
        raise ValueError(f"Not a stable semantic version tag: {tag}")

    return version

def shutdown(shutdown_type: int = 0) -> None:
    """Shut down or reboot system

    App has exited with code 0 (=shutdown) or 100 (=reboot)"""
    action = "shut down"

    if int(shutdown_type) == 100:
        action = "reboot"

    if platform.system() == "Windows":
        flag = "r" if action == "reboot" else "s"
        cmd = ["shutdown", f"/{flag}", "/f", "/t", "0"]
    else:
        flag = "r" if action == "reboot" else "h"
        cmd = ["shutdown", f"-{flag}", "now"]

    try:
        # /s = shut down
        # /r = reboot
        # /f = force running apps to close
        # /t 0 = no time delay
        # os.system("shutdown /" + self.shutdown_type + " /f /t 0")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                "Shutdown failed : "
                f"{result.returncode}, {result.stderr}"
            )
    except Exception as e:
        print("Error while shutting down: "
                        + f"{e}")

def main():
    # Check if logs folder exists
    if not os.path.isdir(LOGS_DIR):
        try:
            os.makedirs(LOGS_DIR)
            logger.info("Created logs directory")
        except IOError as e:
            logger.error(f"Failed to create logs directory: {e}")
        except Exception as e:
            logger.error(f"Failed to create logs directory: {e}")

    # Configure logger
    log_filename = os.path.join(
        LOGS_DIR,
        f"log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_filename, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger.info("DIY Studio App Manager started")

    # Change working directory to Git repository
    try:
        os.chdir(REPOSITORY_PATH)
    except OSError as exc:
        logger.error(
            "Failed to change directory to repository '%s': %s",
            REPOSITORY_PATH,
            exc,
        )
        return

    # Update info from Git:
    if not perform_git_action("fetch", "--prune", "--tags", "origin"):
        run_app(REPOSITORY_PATH)
        return

    # Reset only when explicitly allowed; otherwise preserve local changes.
    status_ok, local_changes = get_local_changes()
    if not status_ok:
        logger.warning(
            "Could not determine local Git changes. Starting application "
            "without updating."
        )
        run_app(REPOSITORY_PATH)
        return

    if local_changes:
        logger.warning("Local Git changes detected:\n%s", local_changes)

        if not ALLOW_DESTRUCTIVE_RESET:
            logger.warning(
                "Skipping update/reset to preserve local changes. Set "
                "ALLOW_DESTRUCTIVE_RESET = True to discard changes "
                "on deployed machines."
            )
            run_app(REPOSITORY_PATH)
            return

        logger.warning(
            "Discarding local changes because destructive reset is enabled."
        )

        if not perform_git_action("reset", "--hard"):
            run_app(REPOSITORY_PATH)
            return

    # Check if CHECKOUT_TAG is set and if so: prioritise this
    if CHECKOUT_TAG is not None:
        # Simply try to checkout to whichever tag is specified
        perform_git_action("checkout", CHECKOUT_TAG)
        # Run the application
        run_app(REPOSITORY_PATH)
        return

    # Get local app version
    file_content = ""

    try:
        with open(APP_VERSION_FILE, "r") as f:
            file_content = f.read().strip()
            logger.info(f"Local app info found: {file_content}")
    except Exception as e:
        logger.error(f"Can't find local file info: {e}. Starting application.")
        run_app(REPOSITORY_PATH)
        return

    current_version, current_branch = parse_app_info(file_content)

    if (
        not current_branch
        or (current_branch == "main" and not current_version)
    ):
        # Not much we can do
        logger.info(
            "Did not find current_branch or "
            "appropriate version number for main branch"
        )
        run_app(REPOSITORY_PATH)
        return

    logger.info(f"Currently on branch: {current_branch}")

    if BRANCH != current_branch:
        # Switch branch
        perform_git_action("switch", "-C", BRANCH, f"origin/{BRANCH}")
        run_app(REPOSITORY_PATH)
        return
    elif BRANCH != "main":
        # Pull new commits
        perform_git_action("pull", "origin", BRANCH)
        run_app(REPOSITORY_PATH)
        return

    # From here on we should be on main branch and
    # we can apply the auto-update logic

    # Get remote Git tags for main branch
    result, stdout = retrieve_git_info(
        "tag", "--merged", "origin/main"
    )

    if not stdout:
        stdout = ""

    if not result:
        logger.error("Can't fetch remote tags. Starting application.")
        run_app(REPOSITORY_PATH)
        return

    remote_tags = stdout.splitlines()

    if not current_version:
        current_version = ""

    # Find the tag with the highest patch level
    best_tag = None
    local_version = parse_stable_version(current_version)

    if local_version is None:
        logger.warning(
            "Current main version is not a stable semantic version tag: %s. "
            "Skipping stable patch auto-update.",
            current_version
        )
        run_app(REPOSITORY_PATH)
        return

    highest_patch_level = local_version[2]

    for tag in remote_tags:
        # logger.info(f"Remote tag found: {tag}")
        tag = tag.strip()
        remote_version = parse_stable_version(tag)

        if remote_version is None:
            # Skip if it doesn't match X.X.X
            continue

        if remote_version[0] != local_version[0]:
            # Major number is different, skip
            continue

        if remote_version[1] != local_version[1]:
            # Minor number is different, skip
            continue

        if remote_version[2] > highest_patch_level:
            highest_patch_level = remote_version[2]
            best_tag = tag
            continue

    if best_tag:
        logger.info(f"Update found: {best_tag}")

        # Update
        perform_git_action("checkout", best_tag)
    else:
        logger.info("No update found.")

    # Run the application
    run_app(REPOSITORY_PATH)

if __name__ == "__main__":
    main()
