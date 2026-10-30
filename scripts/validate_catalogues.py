from pathlib import Path

from nvfr.catalogue import Catalogue


def main():
    catalogue = Catalogue.load(Path(__file__).resolve().parents[1] / "src/nvfr/data/catalogues")
    print(f"Validated {len(catalogue.documents)} catalogues and {len(catalogue.packages)} unique packages")


if __name__ == "__main__":
    main()
