import argparse
#Exectution and pipeline
#imports from other .py files
from http_client import get_response


def main():
    parser = argparse.ArgumentParser(description = 'Enumerate and fuzz your web target using automation with python')
    parser.add_argument("-t","--target", required=True , help="Your target host (https://target.com)")
    args = parser.parse_args()
    target = args.target
    get_response(target)

if __name__ == "__main__":
    main()
