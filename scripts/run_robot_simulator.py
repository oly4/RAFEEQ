from pathlib import Path
import sys

ROBOT_SRC = Path(__file__).resolve().parents[1] / "edge" / "robot" / "src"
sys.path.insert(0, str(ROBOT_SRC))

from rafeeq_robot.main import main  # noqa: E402

if __name__ == "__main__":
    main()
