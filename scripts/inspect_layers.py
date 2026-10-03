import glob
import pyogrio

paths = glob.glob("data/bronze/manual/**/*.gdb", recursive=True) + \
        glob.glob("data/bronze/manual/**/*.shp", recursive=True)

for p in paths:
    for name, geom in pyogrio.list_layers(p):
        fields = list(pyogrio.read_info(p, layer=name)["fields"])
        print(p, "|", name, "|", geom, "|", fields)