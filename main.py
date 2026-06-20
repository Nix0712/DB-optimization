from pathlib import Path

from utils.schema import Database 
from sys import argv

def main(*sysargv):
    first_element = sysargv[0]
    m = Database(first_element)
    print(m)
    print("end of main")
    

if __name__ == "__main__":
    main(*argv[1:])