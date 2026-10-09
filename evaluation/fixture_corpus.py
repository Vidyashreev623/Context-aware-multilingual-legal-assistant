"""
Synthetic fixture corpus for Phase 15 evaluation.

IMPORTANT — what this is and isn't:

data_collection/*/collected/ and data/raw/*/ are still empty (spec
section 9 forbids fabricating sources, and this sandbox has no network
to actually fetch real Acts/judgments — see DATASET.md). Phase 15 still
needs *something* real to run Precision@K/Recall@K/MRR/Hit Rate
against, "no fabricated evaluation results" (Rule 4) means: don't
invent numbers — it doesn't mean the harness itself can't exist yet.

So this file is a small, hand-written set of chunks that:
  - name REAL, well-known Indian Acts/sections (Indian Contract Act
    s.10, IT Act s.66C, Consumer Protection Act, Hindu Marriage Act,
    Transfer of Property Act, Industrial Disputes Act) — nothing here
    is an invented citation.
  - contain ORIGINAL summary text written for this fixture, NOT copied
    from any actual Act/judgment text, and explicitly NOT to be treated
    as authoritative legal text.
  - exist ONLY so evaluate.py has a real, reproducible corpus + query
    set to measure baseline-vs-improved retrieval behaviour on.

Before generating the report numbers spec section 46 asks for, replace
this fixture with the real collected+processed+embedded corpus (Phases
2-5 run for real, on a machine with network access) and re-run
evaluate.py against it. Everything evaluate.py computes from whatever
corpus it's given is real, un-fabricated arithmetic either way.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FixtureChunk:
    chunk_id: str
    domain: str
    act_name: str
    section: str | None
    document_type: str
    jurisdiction: str
    language: str
    text: str
    year: int | None = None


CORPUS: list[FixtureChunk] = [
    # --- contract ---
    FixtureChunk(
        "contract_ica_010_001", "contract", "Indian Contract Act, 1872", "10",
        "act", "India", "en",
        "An agreement is a contract when it is made by the free consent of "
        "parties competent to contract, for a lawful consideration and "
        "lawful object, and is not expressly declared void.",
        1872,
    ),
    FixtureChunk(
        "contract_ica_073_001", "contract", "Indian Contract Act, 1872", "73",
        "act", "India", "en",
        "When a contract is broken, the party who suffers by the breach is "
        "entitled to receive compensation for any loss or damage caused to "
        "them which naturally arose in the usual course of things from the "
        "breach.",
        1872,
    ),
    FixtureChunk(
        "contract_ica_124_001", "contract", "Indian Contract Act, 1872", "124",
        "act", "India", "en",
        "A contract of indemnity is a contract by which one party promises "
        "to save the other from loss caused by the conduct of the promisor "
        "or any other person.",
        1872,
    ),
    # --- cyber ---
    FixtureChunk(
        "cyber_it_066c_001", "cyber", "Information Technology Act, 2000", "66C",
        "act", "India", "en",
        "Whoever fraudulently or dishonestly makes use of the electronic "
        "signature, password, or any other unique identification feature of "
        "any other person is said to commit identity theft and is "
        "punishable with imprisonment and fine.",
        2000,
    ),
    FixtureChunk(
        "cyber_it_066d_001", "cyber", "Information Technology Act, 2000", "66D",
        "act", "India", "en",
        "Whoever cheats by personation by means of a communication device "
        "or a computer resource shall be punished with imprisonment and "
        "fine.",
        2000,
    ),
    FixtureChunk(
        "cyber_it_043_001", "cyber", "Information Technology Act, 2000", "43",
        "act", "India", "en",
        "If any person, without permission, accesses or secures access to a "
        "computer, computer system or network, they are liable to pay "
        "damages by way of compensation to the person affected.",
        2000,
    ),
    # --- consumer ---
    FixtureChunk(
        "consumer_cpa_002_001", "consumer", "Consumer Protection Act, 2019", "2",
        "act", "India", "en",
        "A 'deficiency' means any fault, imperfection, shortcoming or "
        "inadequacy in the quality, nature and manner of performance of a "
        "service that a trader is required to maintain.",
        2019,
    ),
    FixtureChunk(
        "consumer_cpa_035_001", "consumer", "Consumer Protection Act, 2019", "35",
        "act", "India", "en",
        "A complaint relating to a defective good or deficient service may "
        "be filed by a consumer before the District Consumer Disputes "
        "Redressal Commission.",
        2019,
    ),
    # --- family ---
    FixtureChunk(
        "family_hma_013_001", "family", "Hindu Marriage Act, 1955", "13",
        "act", "India", "en",
        "A marriage may be dissolved by a decree of divorce on grounds "
        "including cruelty, desertion for a continuous period of two years, "
        "or conversion to another religion.",
        1955,
    ),
    FixtureChunk(
        "family_hma_024_001", "family", "Hindu Marriage Act, 1955", "24",
        "act", "India", "en",
        "Either spouse who has no independent income sufficient for support "
        "may apply for maintenance pendente lite and litigation expenses "
        "during the proceedings.",
        1955,
    ),
    # --- property ---
    FixtureChunk(
        "property_tpa_105_001", "property", "Transfer of Property Act, 1882", "105",
        "act", "India", "en",
        "A lease of immovable property is a transfer of a right to enjoy "
        "such property, made for a certain time, in consideration of a "
        "price paid or promised, called rent.",
        1882,
    ),
    FixtureChunk(
        "property_tpa_106_001", "property", "Transfer of Property Act, 1882", "106",
        "act", "India", "en",
        "In the absence of a contract to the contrary, a lease of "
        "immovable property for agricultural or manufacturing purposes "
        "requires six months' notice to terminate; for any other purpose, "
        "fifteen days' notice.",
        1882,
    ),
    # --- employment ---
    FixtureChunk(
        "employment_ida_025f_001", "employment", "Industrial Disputes Act, 1947", "25F",
        "act", "India", "en",
        "No workman employed in any industry who has been in continuous "
        "service for not less than one year shall be retrenched without one "
        "month's notice and payment of retrenchment compensation.",
        1947,
    ),
    FixtureChunk(
        "employment_ida_002a_001", "employment", "Industrial Disputes Act, 1947", "2A",
        "act", "India", "en",
        "Where an employer discharges, dismisses, retrenches or otherwise "
        "terminates the services of an individual workman, that itself is "
        "deemed to be an industrial dispute.",
        1947,
    ),
    # --- Hindi translations (same underlying provisions, spec section 47) ---
    FixtureChunk(
        "cyber_it_066c_001_hi", "cyber", "Information Technology Act, 2000", "66C",
        "act", "India", "hi",
        "जो कोई भी किसी अन्य व्यक्ति के इलेक्ट्रॉनिक हस्ताक्षर, पासवर्ड या "
        "किसी अन्य विशिष्ट पहचान सुविधा का धोखाधड़ी से उपयोग करता है, वह "
        "पहचान की चोरी का दोषी माना जाता है।",
        2000,
    ),
    FixtureChunk(
        "contract_ica_010_001_hi", "contract", "Indian Contract Act, 1872", "10",
        "act", "India", "hi",
        "एक समझौता तब अनुबंध बनता है जब वह पक्षों की स्वतंत्र सहमति से, "
        "वैध प्रतिफल और वैध उद्देश्य के लिए किया गया हो।",
        1872,
    ),
    # --- Kannada translations ---
    FixtureChunk(
        "cyber_it_066c_001_kn", "cyber", "Information Technology Act, 2000", "66C",
        "act", "India", "kn",
        "ಯಾವುದೇ ವ್ಯಕ್ತಿಯ ಎಲೆಕ್ಟ್ರಾನಿಕ್ ಸಹಿ, ಪಾಸ್‌ವರ್ಡ್ ಅಥವಾ ಇತರ ವಿಶಿಷ್ಟ "
        "ಗುರುತಿನ ವೈಶಿಷ್ಟ್ಯವನ್ನು ಮೋಸದಿಂದ ಬಳಸುವವರು ಗುರುತಿನ ಕಳ್ಳತನ ಎಸಗಿದಂತೆ.",
        2000,
    ),
    FixtureChunk(
        "contract_ica_010_001_kn", "contract", "Indian Contract Act, 1872", "10",
        "act", "India", "kn",
        "ಪಕ್ಷಗಳ ಸ್ವತಂತ್ರ ಒಪ್ಪಿಗೆಯಿಂದ, ಕಾನೂನುಬದ್ಧ ಪ್ರತಿಫಲ ಮತ್ತು ಉದ್ದೇಶಕ್ಕಾಗಿ "
        "ಮಾಡಿದ ಒಪ್ಪಂದವು ಕಾನೂನುಬದ್ಧ ಒಪ್ಪಂದವಾಗುತ್ತದೆ.",
        1872,
    ),
    # --- distractors: plausible but off-domain, to make Precision@K meaningful ---
    FixtureChunk(
        "corporate_ca_166_001", "corporate", "Companies Act, 2013", "166",
        "act", "India", "en",
        "A director of a company shall act in good faith to promote the "
        "objects of the company for the benefit of its members as a whole.",
        2013,
    ),
    FixtureChunk(
        "taxation_it_080c_001", "taxation", "Income Tax Act, 1961", "80C",
        "act", "India", "en",
        "An assessee may claim a deduction for specified investments and "
        "payments, subject to the overall limit prescribed under this "
        "section.",
        1961,
    ),
    FixtureChunk(
        "criminal_ipc_499_001", "criminal", "Indian Penal Code, 1860", "499",
        "act", "India", "en",
        "Whoever makes or publishes any imputation concerning any person, "
        "intending to harm their reputation, is said to defame that "
        "person.",
        1860,
    ),
]
