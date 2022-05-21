# Functions decorated with @task can be run as shell commands using
# the `invoke` command. See Invoke documentation for more information:
#     https://docs.pyinvoke.org/en/stable/index.html
# When adding commands, be cognizant that the invoke command along
# with this file may be executed within older system python versions.


import glob
import os
import shutil

from invoke import Collection, task

default_venv_python = "python3"
precommit_config_basename = ".pre-commit-config.yaml"
ignore_revs_basename = ".git-blame-ignore-revs"

# setting up some directory paths
this_dir = os.path.dirname(os.path.abspath(__file__))
venv_dir = os.path.join(this_dir, "venv")
venv_bin = os.path.join(venv_dir, "bin")
venv_python = os.path.join(venv_bin, "python")


def _ask_y_or_n():
    """Return True for 'yes' and False for 'no'"""
    result = input("Overwrite? [y/n]: ").casefold()
    while result not in ("y", "n"):
        print("Please enter 'y' or 'n'")
        result = input("Overwrite? [y/n]: ").casefold()
    if result == "n":
        return False
    assert result == "y"
    return True


def _validate_venv(c):
    if not os.path.isfile(venv_python):
        raise EnvironmentError("bootstrap virtual environment is not setup")


@task(
    help={
        "python": (
            "the python executable to create the venv from "
            + f"(default: {default_venv_python})"
        ),
        "yes": "answer yes to any intermediate steps",
    },
)
def create_venv(c, python=default_venv_python, yes=False):
    """Build the main python virtual environment from scratch."""
    if os.path.exists(venv_dir):
        print(f"venv directory exists: '{venv_dir}'")
        if not yes:
            if not _ask_y_or_n():
                exit()
        print(f"deleting directory '{venv_dir}'")
        shutil.rmtree(venv_dir)
    rc = c.run(f"{python} -m venv {venv_dir}")
    assert rc.ok
    print(f"venv created at '{venv_dir}'")
    rc = c.run(f"{venv_python} -m pip install -U pip setuptools wheel", echo=True)
    assert rc.ok
    rc = c.run(
        f"{venv_python} -m pip install -U pre-commit pip-tools",
        echo=True,
    )


@task
def install_git_hooks(c):
    """Install project-local git pre-commit hooks and blame configurations."""
    _validate_venv(c)
    # install the pre-commit hooks if there is a config file
    if os.path.exists(os.path.join(this_dir, precommit_config_basename)):
        with c.cd(this_dir):
            rc = c.run(f"{venv_python} -m pre_commit install", echo=True)
            assert rc.ok
    # install the --ignore-rev defaults if there is a file tracking them
    if os.path.exists(os.path.join(this_dir, ignore_revs_basename)):
        with c.cd(this_dir):
            rc = c.run(
                f"git config --local blame.ignoreRevsFile {ignore_revs_basename}",
                echo=True,
            )
            assert rc.ok


@task
def install_project(c):
    """Install project into the virtual environment."""
    _validate_venv(c)
    for req in glob.glob(os.path.join(this_dir, "requirements*.txt")):
        rc = c.run(f"{venv_python} -m pip install -r {req}", echo=True)
        assert rc.ok


@task(
    help={
        "python": (
            "the python executable to create the venv from "
            + f"(default: {default_venv_python})"
        ),
        "yes": "answer yes to any intermediate steps",
    },
)
def bootstrap_default(c, python=default_venv_python, yes=False):
    """Bootstrap the development environment (runs all sub-commands)."""
    create_venv(c, python=python, yes=yes)
    install_git_hooks(c)
    install_project(c)
    print("\n\nBootstrap complete. Activate your virtual environment with:")
    print(f"    source {venv_bin}/activate\n\n")


@task(
    help={
        "upgrade": "optional package to upgrade (e.g., 'django<1.0')",
    },
)
def pip_compile(c, upgrade=None):
    """Run the pip-compile process on all projects."""
    _validate_venv(c)
    # check this so we know if we need to update the fully-qualified invoke command we
    # put at the top of the requirements file
    assert dev.tasks["pip-compile"] is pip_compile
    task_name = "dev.pip-compile"
    # try to make sure to process these in order
    priority = {
        "requirements.in": float("-inf"),
        "requirements-test.in": float("inf"),
    }
    for req in sorted(
        glob.glob(os.path.join(this_dir, "requirements*.in")),
        key=lambda _: (priority.get(os.path.basename(_), 0), _),
    ):
        req_dirname = os.path.dirname(req)
        req_filename = os.path.basename(req)
        args = ""
        args += f" --output-file={req_filename.replace('.in', '.txt')}"
        args += f" {req_filename}"
        # this will add a message to the requirements files about
        # how they were generated
        msg = f"pip-compile {args}\n#\n"
        msg += "# or run the following command from the project directory:\n#\n"
        msg += f"#    invoke {task_name}"
        cmd = (
            f"CUSTOM_COMPILE_COMMAND='{msg}' {venv_python} "
            + f"-m piptools compile {args}"
        )
        if upgrade is not None:
            cmd += f" --upgrade-package '{upgrade}'"
        with c.cd(req_dirname):
            c.run(cmd, echo=True, hide="both")


@task
def upgrade_pre_commit(c):
    """Upgrade and reinstall the git pre-commit checks for every project."""
    _validate_venv(c)
    rc = c.run(f"{venv_python} -m pip install -U pre-commit", echo=True)
    assert rc.ok
    with c.cd(this_dir):
        if os.path.exists(os.path.join(this_dir, precommit_config_basename)):
            rc = c.run(f"{venv_python} -m pre_commit autoupdate", echo=True)
    install_git_hooks(c)


ns = Collection()
bootstrap = Collection("bootstrap")
bootstrap.add_task(bootstrap_default, name="_default_", default=True)
bootstrap.add_task(create_venv)
bootstrap.add_task(install_git_hooks)
bootstrap.add_task(install_project)
ns.add_collection(bootstrap)
dev = Collection("dev")
dev.add_task(pip_compile)
dev.add_task(upgrade_pre_commit)
ns.add_collection(dev)
