# load the environment variables for this setup
from dotenv import find_dotenv, load_dotenv

from yoker_chat import run

_ = load_dotenv(find_dotenv())
_ = load_dotenv(find_dotenv(".env.local"))

if __name__ == "__main__":
  run()
