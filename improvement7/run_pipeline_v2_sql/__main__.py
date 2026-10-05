"""Use the same explicit CLI for module and script launches."""
import runpy

if __name__ == "__main__":
    runpy.run_module(__package__ + ".run", run_name="__main__")
