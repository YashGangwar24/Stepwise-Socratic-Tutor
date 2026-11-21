"""Conservative subject mismatch detection for the current StepWise subjects."""

import re


SUBJECTS = ("Algorithms", "LAW", "Biology", "DBMS", "Mathematics")

# A prompt is blocked only when it contains a recognizable topic from a
# different supported subject and contains no recognizable topic from the
# selected subject. Generic words are deliberately excluded to reduce false
# positives. This is a lightweight guard, not a full semantic classifier.
TOPIC_TERMS = {
    "Algorithms": (
        "algorithm", "algorithms", "sorting", "sort", "binary search", "searching algorithm",
        "recursion", "data structure", "graph traversal", "bfs", "dfs", "big o",
        "time complexity", "space complexity", "complexity analysis", "array", "linked list",
        "stack", "queue", "binary tree", "heap", "hash table", "dynamic programming",
        "greedy algorithm", "shortest path", "loop invariant", "pseudocode",
    ),
    "LAW": (
        "legal", "constitution", "fundamental right", "article 21", "article 14",
        "article 19", "article 32", "article 370", "supreme court", "high court", "judiciary",
        "legislation", "statute", "writ petition", "parliament", "constitutional amendment",
        "indian penal code", "ipc", "bns", "contract law", "tort law", "legal precedent",
        "criminal law", "civil law",
    ),
    "Biology": (
        "biology", "photosynthesis", "mitosis", "meiosis", "dna", "rna", "gene", "genetics",
        "cell membrane", "cell division", "organism", "enzyme", "protein synthesis", "evolution",
        "ecosystem", "chlorophyll", "chromosome", "biodiversity", "respiration in plants",
    ),
    "DBMS": (
        "dbms", "database", "sql", "select statement", "database query", "primary key",
        "foreign key", "normalization", "normalisation", "acid property", "database transaction",
        "database index", "relational algebra", "relational database", "database schema",
        "inner join", "left join", "mongodb", "nosql", "entity relationship diagram",
    ),
    "Mathematics": (
        "mathematics", "algebra", "calculus", "derivative", "integration", "integral", "matrix",
        "matrices", "determinant", "probability", "statistics", "theorem", "geometry",
        "trigonometry", "polynomial", "logarithm", "differential equation", "arithmetic sequence",
        "quadratic equation", "linear equation", "limit of a function",
    ),
}

ALIASES = {"constitution of india": "LAW", "law": "LAW"}


def canonical_subject(subject: str) -> str:
    normalized = " ".join((subject or "").strip().lower().split())
    if normalized in ALIASES:
        return ALIASES[normalized]
    return next((item for item in SUBJECTS if item.lower() == normalized), subject)


def mismatched_subject(message: str, selected_subject: str) -> str | None:
    """Return the detected different subject, or None when no clear mismatch exists."""
    selected = canonical_subject(selected_subject)
    if selected not in TOPIC_TERMS:
        return None

    text = (message or "").lower()
    detected = set()
    for subject, terms in TOPIC_TERMS.items():
        for term in terms:
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
                detected.add(subject)
                break

    if selected not in detected and detected:
        # A cross-topic prompt can still be relevant to the selected subject;
        # allow it whenever we found evidence for the selected subject as well.
        return sorted(detected)[0]
    return None


def scope_redirect(selected_subject: str, detected_subject: str) -> str:
    return (
        f"This question looks like it belongs to {detected_subject}, but this chat is set to "
        f"{canonical_subject(selected_subject)}. I’ll keep this chat focused on its selected subject. "
        f"Please switch the subject to {detected_subject} or ask a {canonical_subject(selected_subject)} question."
    )
