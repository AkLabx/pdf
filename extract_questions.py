
import os
import re
import json
import logging
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Constants
OUTPUT_DIR = "."

# Mapping based on user approval
FILENAME_TO_EXAM_MAP = {
    "1-5 TRE 2.0.pdf": "BPSC TRE 2.0 (1-5)",
    "1-5.pdf": "BPSC TRE 1.0 (1-5)",
    "6-8 MATHS SCIENCE (1).pdf": "BPSC TRE 2.0 (6-8 Maths Science)",
    "6-8 MATHS SCIENCE.pdf": "BPSC TRE 2.0 (6-8 Maths Science)",
    "6-8 SOCIAL SCIENCE.pdf": "BPSC TRE 2.0 (6-8 Social Science)",
    "9-10 MATHS TRE 1.0.pdf": "BPSC TRE 1.0 (9-10 Maths)",
    "9-10 SCIENCE (1).pdf": "BPSC TRE 1.0 (9-10 Science)",
    "9-10 SCIENCE TRE -1.0.pdf": "BPSC TRE 1.0 (9-10 Science)",
    "9-10 SCIENCE.pdf": "BPSC TRE 1.0 (9-10 Science)",
    "9-10 SOCIAL SCIENCE TRE 2.0.pdf": "BPSC TRE 2.0 (9-10 Social Science)",
    "9-10 Social Science.pdf": "BPSC TRE 1.0 (9-10 Social Science)",
    "9-10 social science (1).pdf": "BPSC TRE 1.0 (9-10 Social Science)",
    "BPSC - DSO PT 2025.pdf": "BPSC DSO PT 2025",
    "BPSC - Mineral Development Officer Exam 2025 - GS Paper.pdf": "BPSC Mineral Dev Officer 2025",
    "BPSC Law Officer GS Question Paper.pdf": "BPSC Law Officer GS",
    "BPSC Motor Vehicle Inspectors. QP.pdf": "BPSC Motor Vehicle Inspector",
    "BPSC Public Relation Officer GS Question Paper.pdf": "BPSC PRO GS",
    "BSSC FIELD ASSISTANT EXAMINATION 10-8-2025 QUESTIONS.pdf": "BSSC Field Assistant 2025",
    "Pyq BPSC.pdf": "BPSC PYQ Generic"
}

# Regex Patterns
# Detects start of question: "1.", "10.", "Q1.", "Q 1.", "H-10.", "E-10."
REGEX_QUESTION_START = re.compile(r'^\s*(?:Q\.?|Question)?\s*([A-Z]-)?(\d+)\s*[\.\)]\s+(.*)', re.IGNORECASE)

# Detects options: "(A)", "(b)", "A)", "A.", "1)", "(1)"
REGEX_OPTION_START = re.compile(r'^\s*(?:\(([A-Za-z0-9])\)|([A-Za-z0-9])[\)\.])\s+(.*)')

# Keywords to skip instruction blocks
SKIP_KEYWORDS = ["Instructions", "Time Allowed", "Maximum Marks", "Rough Work", "Booklet Series", "Candidate’s Roll Number"]

def is_hindi(text):
    """Checks if the text contains Hindi characters."""
    return any('\u0900' <= char <= '\u097f' for char in text)

def extract_text_from_pdf(pdf_path):
    """
    Converts PDF to images, splits them (assuming 2 columns), and OCRs them.
    Returns a list of strings (lines) from the entire PDF.
    """
    logging.info(f"Processing {pdf_path}...")
    try:
        # Using thread_count to maybe speed up? or just 1 to avoid OOM
        images = convert_from_path(pdf_path, thread_count=2)
    except Exception as e:
        logging.error(f"Failed to convert PDF {pdf_path}: {e}")
        return []

    full_text_lines = []

    for i, img in enumerate(images):
        # logging.info(f"OCR Page {i+1}/{len(images)}")
        width, height = img.size
        left_img = img.crop((0, 0, width // 2, height))
        right_img = img.crop((width // 2, 0, width, height))

        # OCR with both languages
        # psm 6 is "Assume a single uniform block of text".
        # This might be faster than default psm 3.
        try:
            text_left = pytesseract.image_to_string(left_img, lang='eng+hin', config='--psm 6')
            text_right = pytesseract.image_to_string(right_img, lang='eng+hin', config='--psm 6')

            full_text_lines.extend(text_left.split('\n'))
            full_text_lines.extend(text_right.split('\n'))
        except Exception as e:
            logging.error(f"OCR Error on page {i+1}: {e}")

    return full_text_lines

def parse_questions(lines, exam_name, classification_stub):
    """
    Parses lines of text into Question Objects.
    """
    questions_map = {} # Map ID (number) to Question Object

    # Clean lines
    cleaned_lines = [line.strip() for line in lines if line.strip()]

    # State tracking
    current_q_obj = None

    for line in cleaned_lines:
        # Check if line is an instruction/noise
        if any(k.lower() in line.lower() for k in SKIP_KEYWORDS):
            continue

        # Check for Question Start
        q_match = REGEX_QUESTION_START.match(line)
        if q_match:
            # Group 1: Prefix (H-, E-), Group 2: Number, Group 3: Text
            q_num_str = q_match.group(2)
            q_text = q_match.group(3)

            q_id = q_num_str

            # Check if we already have this question
            if q_id not in questions_map:
                questions_map[q_id] = {
                    "id": f"UNK{q_id}",
                    "sourceInfo": {
                        "examName": exam_name,
                        "examYear": 2023,
                        "examDateShift": "Unknown"
                    },
                    "classification": classification_stub,
                    "tags": [],
                    "properties": {
                        "difficulty": "Medium",
                        "questionType": "MCQ"
                    },
                    "question": "",
                    "question_hi": "",
                    "options": [],
                    "options_hi": [],
                    "correct": "",
                    "explanation": {
                        "summary": "",
                        "analysis_correct": "",
                        "analysis_incorrect": "",
                        "conclusion": "",
                        "fact": ""
                    }
                }

            current_q_obj = questions_map[q_id]

            # Detect language of the question text
            if is_hindi(q_text):
                if current_q_obj["question_hi"]:
                     current_q_obj["question_hi"] += " " + q_text
                else:
                    current_q_obj["question_hi"] = q_text
            else:
                if current_q_obj["question"]:
                    current_q_obj["question"] += " " + q_text
                else:
                    current_q_obj["question"] = q_text

            continue

        # Check for Option
        opt_match = REGEX_OPTION_START.match(line)
        if opt_match and current_q_obj:
            opt_text = opt_match.group(3)

            # Detect language
            if is_hindi(opt_text):
                current_q_obj["options_hi"].append(opt_text)
            else:
                current_q_obj["options"].append(opt_text)
            continue

        # Continuation of text
        if current_q_obj:
            line_is_hindi = is_hindi(line)

            if line_is_hindi:
                if current_q_obj["options_hi"]:
                    current_q_obj["options_hi"][-1] += " " + line
                else:
                    current_q_obj["question_hi"] += " " + line
            else:
                if current_q_obj["options"]:
                    current_q_obj["options"][-1] += " " + line
                else:
                    current_q_obj["question"] += " " + line

    # Sort by ID (integer conversion)
    sorted_questions = sorted(questions_map.values(), key=lambda x: int(x['id'].replace('UNK', '')) if x['id'].replace('UNK', '').isdigit() else 0)
    return sorted_questions

def process_file(filename):
    if not filename.lower().endswith(".pdf"):
        return

    exam_name = FILENAME_TO_EXAM_MAP.get(filename, "Generic Exam")

    print(f"Processing {filename} as {exam_name}...")
    lines = extract_text_from_pdf(filename)

    # Classification stub
    classification = {
        "subject": "Unknown",
        "topic": "Unknown",
        "subTopic": "Unknown"
    }

    questions = parse_questions(lines, exam_name, classification)

    # Filter out empty questions (artifacts)
    valid_questions = []
    for q in questions:
        # A valid question should have at least some text in Q or Q_hi
        if not q["question"] and not q["question_hi"]:
            continue
        # Also filter if it looks like just instructions (long text, no options)
        if (len(q["question"]) > 500 or len(q["question_hi"]) > 500) and not q["options"] and not q["options_hi"]:
            continue

        valid_questions.append(q)

    # Output JSON
    out_filename = os.path.splitext(filename)[0] + ".json"
    with open(out_filename, "w", encoding="utf-8") as f:
        json.dump(valid_questions, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(valid_questions)} questions to {out_filename}")

if __name__ == "__main__":
    files = [f for f in os.listdir(".") if f.lower().endswith(".pdf")]
    files.sort()

    for f in files:
        # Skip if JSON exists and is not empty (size > 100 bytes)
        json_path = os.path.splitext(f)[0] + ".json"
        if os.path.exists(json_path) and os.path.getsize(json_path) > 100:
            print(f"Skipping {f} as {json_path} already exists.")
            continue

        try:
            process_file(f)
        except Exception as e:
            print(f"Skipping {f} due to error: {e}")
