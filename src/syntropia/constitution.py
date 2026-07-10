import os
from typing import Tuple, Dict, Any


class ConstitutionGuard:
    """
    Enforces the 12 Unbreakable Rules of Syntropia's Constitution on all proposed mutations.
    """

    def __init__(self, max_timeout_ticks: int = 30, restricted_paths: list = None):
        self.max_timeout_ticks = max_timeout_ticks
        self.restricted_paths = restricted_paths or [
            "src/syntropia/engine.py",
            "src/syntropia/orchestrator.py",
            "src/syntropia/registry.py",
            "src/syntropia/crypto.py",
            "src/syntropia/constitution.py",
            "src/syntropia/blockchain.py",
        ]

    def check_mutation(self, proposal: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates a proposed agent mutation against the hardcoded constitutional rules.
        Returns: (is_approved: bool, reason_or_status: str)
        """
        # Rule 1: Self-Preservation (No modifications to restricted core engine directories/files)
        target_file = proposal.get("target_file", "")
        if target_file:
            normalized_target = os.path.normpath(target_file)
            for rest_path in self.restricted_paths:
                if normalized_target.startswith(os.path.normpath(rest_path)):
                    return False, f"Rule 1 Violaton (Self-Preservation): Cannot mutate core engine component: {rest_path}"

        # Rule 2: Resource Efficiency (Bounds verification)
        timeout = proposal.get("timeout")
        if timeout is not None:
            if not isinstance(timeout, int) or timeout <= 0:
                return False, "Rule 7 Violation (No Infinite Loops): Timeout must be a positive integer"
            if timeout > self.max_timeout_ticks:
                return False, f"Rule 2 Violation (Resource Efficiency): Timeout of {timeout} exceeds system limit of {self.max_timeout_ticks} ticks"

        limits = proposal.get("limits", {})
        if limits:
            # Check maximum memory limit (e.g. max 1024 MB per script container)
            memory_mb = limits.get("memory_mb", 0)
            if memory_mb > 1024:
                return False, f"Rule 2 Violation (Resource Efficiency): Memory limit {memory_mb}MB exceeds maximum container allowance (1024MB)"

        # Rule 3: Auditable Evolution (Must be signed by parent/proposer key)
        signature = proposal.get("signature")
        proposer_key = proposal.get("proposer_key")
        if not signature or not proposer_key:
            return False, "Rule 3 Violation (Auditable Evolution): Mutation proposal must be cryptographically signed by proposer"

        # Rule 6: Sandbox Whitelisting / No Malicious Code (Static check for dangerous patterns)
        code_diff = proposal.get("code_diff", "")
        if code_diff:
            # Check for banned constructs in the script code
            dangerous_patterns = [
                "os.system",
                "subprocess.Popen",
                "subprocess.call",
                "import os",  # unless sandboxed imports are allowed
                "__import__",
                "eval(",
                "exec(",
                "shutil.rmtree('/')",
            ]
            for pattern in dangerous_patterns:
                if pattern in code_diff:
                    return False, f"Rule 6 Violation (Sandbox Whitelisting): Code contains restricted pattern: '{pattern}'"

        # Rule 7: Timeout Safeguards / No Infinite Loops
        if "timeout" not in proposal:
            return False, "Rule 7 Violation (No Infinite Loops): Mutation proposal must explicitly specify an execution timeout"

        # Rule 10: Revert to Safe State (Must specify fallback commit or previous block hash)
        last_safe_hash = proposal.get("last_safe_hash")
        if not last_safe_hash:
            return False, "Rule 10 Violation (Fallback to Safe State): Proposal must link to the last verified safe state block hash"

        # Rule 11: The North Star (Must show objective benchmark improvements: lower latency or lower footprint)
        benchmarks = proposal.get("benchmarks", {})
        if not benchmarks:
            return False, "Rule 11 Violation (The North Star): Proposal must include signed benchmark measurements"
        
        # Verify benchmark improves over baseline (e.g., latency must be less than baseline)
        baseline_latency = proposal.get("baseline_latency", float("inf"))
        new_latency = benchmarks.get("latency_ms", float("inf"))
        
        baseline_security = proposal.get("baseline_syscall_count", 100)
        new_security = benchmarks.get("syscall_count", 100)

        # Mutation must be faster (lower latency) OR more secure (fewer syscalls)
        is_faster = new_latency < baseline_latency
        is_more_secure = new_security < baseline_security

        if not (is_faster or is_more_secure):
            return False, (f"Rule 11 Violation (The North Star): Mutation is neither faster "
                           f"(Latency: {new_latency}ms vs {baseline_latency}ms) "
                           f"nor more secure (Syscalls: {new_security} vs {baseline_security})")

        # Stubs for rules 4, 5, 8, 9, 12 (governed on network level)
        # Passed all local constraints
        return True, "Approved"
