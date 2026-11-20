"""Search strings for the classroom-monitoring-software evidence scan.

Written in Semantic Scholar bulk-search syntax:
``|`` = OR, ``+`` = AND, ``*`` = prefix wildcard, ``"..."`` = phrase, ``()`` = grouping.
Bulk search matches title and abstract only, so product names are paired with
generic descriptions of the same software category.
"""

from __future__ import annotations

SCHOOL_CONTEXT = "(school* | classroom* | student* | pupil* | teacher*)"

# Vendor and product names. Ambiguous names (Impero, Gaggle, Bark, Vision, Insight)
# are only matched together with a school context term.
PRODUCT_NAMES = (
    "goguardian | linewize | classwize | securly | lanschool | dyknow | blocksi "
    '| hapara | veyon | italc | mythware | "netsupport school" | "netsupport manager" '
    '| "lightspeed classroom" | "lightspeed systems" | "apple classroom" '
    '| "netop vision" | "netop school" | "faronics insight" | "smart sync" '
    '| "family zone" | "qustodio" | "senso.cloud" | "smoothwall" | "bark for schools" '
    '| "chrome education upgrade"'
)

AMBIGUOUS_PRODUCT_NAMES = '(impero | gaggle | "radix viso" | "classroom.cloud" | "class policy")'

SOFTWARE_CATEGORY = (
    '"classroom management software" | "classroom management system" '
    '| "classroom monitoring software" | "classroom monitoring system" '
    '| "screen monitoring software" | "screen monitoring" '
    '| "student monitoring software" | "student activity monitoring" '
    '| "computer monitoring software" | "device monitoring software" '
    '| "remote monitoring software" | "lab management software" '
    '| "monitoring software" | "surveillance software"'
)

SURVEILLANCE_TERMS = (
    '"student surveillance" | "school surveillance" | "classroom surveillance" '
    '| "digital surveillance" | "dataveillance" | "online monitoring" '
    '| "student activity monitoring" | "edtech surveillance"'
)

DEVICE_TERMS = '(laptop* | chromebook* | tablet* | ipad* | computer* | "1:1" | "one-to-one" | device*)'

OFF_TASK_TERMS = (
    '("off-task" | "off task" | distract* | "media multitasking" | multitasking '
    '| "cyberslacking" | "cyberloafing" | "non-academic use")'
)

RESTRICTION_TERMS = (
    "(monitor* | block* | restrict* | filter* | surveil* | lock* "
    '| "self-control" | "self-regulation")'
)

BLOCKING_TERMS = (
    '"website blocking" | "website blocker" | "site blocker" | "internet blocking" '
    '| "web filtering" | "internet filtering" | "content filtering" '
    '| "internet blocker" | "app blocker" | "distraction blocking" | "distraction blocker"'
)

TRIAL_TERMS = (
    '(randomized | randomised | "randomly assigned" | RCT | experiment* '
    '| "quasi-experimental" | "controlled trial" | "control group")'
)

# name -> query. Names are recorded against every paper they retrieve so the
# contribution of each search string can be reported.
QUERIES: dict[str, str] = {
    "product_names": f"({PRODUCT_NAMES})",
    "ambiguous_product_names": f"{AMBIGUOUS_PRODUCT_NAMES} + {SCHOOL_CONTEXT}",
    "software_category": f"({SOFTWARE_CATEGORY}) + {SCHOOL_CONTEXT}",
    "surveillance": f"({SURVEILLANCE_TERMS}) + {SCHOOL_CONTEXT} + {DEVICE_TERMS}",
    "off_task_restriction": (
        f"{DEVICE_TERMS} + (classroom* | lecture* | lesson*) + {OFF_TASK_TERMS} "
        f"+ {RESTRICTION_TERMS}"
    ),
    "blocking": f"({BLOCKING_TERMS}) + {SCHOOL_CONTEXT}",
    "off_task_trials": (
        f"{DEVICE_TERMS} + (classroom* | lecture* | lesson*) + {OFF_TASK_TERMS} + {TRIAL_TERMS}"
    ),
}
