from . import download
from . import clean
from . import chunk

def main():
    print("\n=== Running Phase 1 ===")

    download.wikipedia_data()

    print("\n=== Phase 1 Completed ===")

    print("\n=== Running Phase 2 ===")

    clean.wikipedia_data()

    print("\n=== Phase 2 Completed ===")
    
    print("\n=== Running Phase 3 ===")
    
    chunk.execute()

    print("\n=== Phase 3 Completed ===")

    print("\n=== Running Phase 4 ===")

    # TODO: Call the embed initiator function here.
    print("To be completed...")

    print("\n=== Phase 4 Completed ===")
    
    

if __name__ == "__main__":
    main()