"""Run bronze -> silver -> gold in order."""
from wildfire.pipeline import bronze, silver, gold

if __name__ == "__main__":
    bronze.main()
    silver.main()
    gold.main()
