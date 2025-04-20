
import sys
import os
import argparse
import subprocess

def build(debug: bool = False):
    cur_dir = os.path.abspath(os.path.dirname(__file__))
    # Only include appicon.ico as a data file if needed beyond the icon.
    icon_data = f"--add-data={os.path.join(cur_dir, 'DemoViewer', 'appicon.ico')};DemoViewer"
    external_data = f"--add-data={os.path.join(cur_dir, 'DemoViewer', 'common')};DemoViewer\common"
    additional_path = cur_dir

    # Check for the application icon.
    icon_path = os.path.join(cur_dir, "DemoViewer", "appicon.ico")
    icon_option = f"--icon={icon_path}"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "DemoViewer",
        "--paths", additional_path,
        "--hidden-import", "pyarrow",
        "--hidden-import", "polars",
        "--hidden-import", "scipy",
        "--hidden-import", "matplotlib",
        "--hidden-import", "demoparser2",
        icon_data,
        icon_option,
        external_data,
        "DemoViewer/__main__.py"
    ]

    if debug:
        # In debug mode, don't use --onefile for easier debugging
        cmd.append("--windowed")
        print("Building in debug mode (not using --onefile)")
    else:
        # In release mode, use --onefile and --windowed
        cmd.extend(["--onefile", "--windowed"])

    print("Running command:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

def main():
    parser = argparse.ArgumentParser(description="Build DemoViewer using PyInstaller.")
    parser.add_argument("--debug", action="store_true", help="Build in debug mode (remove --onefile).")
    args = parser.parse_args()
    build(debug=args.debug)

if __name__ == "__main__":
    main()
