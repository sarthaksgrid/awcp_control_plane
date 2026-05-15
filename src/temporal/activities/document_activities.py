from temporalio import activity
import asyncio
from PyPDF2 import PdfReader


@activity.defn
async def extract_text(file_path: str):

    print("========== ACTIVITY-1 ==========")
    print("Extracting text from PDF...")

    reader = PdfReader(file_path)

    text = ""

    for page in reader.pages:
        extracted = page.extract_text()

        if extracted:
            text += extracted

    await asyncio.sleep(2)

    print("TEXT EXTRACTED:")
    print(text)

    return text


@activity.defn
async def summarize_text(text: str):

    print("========== ACTIVITY-2 ==========")
    print("Summarizing text...")

    await asyncio.sleep(3)

    summary = text[:100]

    print("SUMMARY:")
    print(summary)

    return summary


@activity.defn
async def save_summary(summary: str):

    print("========== ACTIVITY-3 ==========")
    print("Saving summary...")

    with open("summary.txt", "w") as f:
        f.write(summary)

    await asyncio.sleep(1)

    print("Summary saved")

    return "saved"


@activity.defn
async def send_email():

    print("========== ACTIVITY-4 ==========")
    print("Sending email notification...")

    await asyncio.sleep(1)

    print("Email sent")

    return "email sent"