import argparse
#Exectution and pipeline
#imports from other .py files



def main():
    parser = argparse.ArgumentParser(description = 'Enumerate and fuzz your web target using automation with python')
    parser.add_argument("-t","--target", required=True , help="Your target host (https://target.com)")
    args = parser.parse_args()


if __name__ == "__main__":
    main()
