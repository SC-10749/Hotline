"""Compatibility entrypoint for the Execution Worker."""

from ...workers.execution_worker import ExecutionWorker, build_worker, main

__all__ = ["ExecutionWorker", "build_worker", "main"]


if __name__ == "__main__":
    main()
