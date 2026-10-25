from softwiki.intelligence.answer_engine import _classify_question


def test_research_questions_are_not_admin():
    assert _classify_question("What registers does the PL031 RTC provide?") == "knowledge"
    assert _classify_question("List the main registers of the PL031 RTC.") == "knowledge"
    assert _classify_question("Summarize the PL031 registers from the knowledge base.") == "knowledge"
    assert _classify_question("How many registers does PL031 have?") == "knowledge"
    assert _classify_question("知识库中 PL031 有哪些寄存器？") == "knowledge"


def test_inventory_questions_are_admin():
    assert _classify_question("What's in my knowledge base?") == "admin"
    assert _classify_question("How many documents are there?") == "admin"
    assert _classify_question("List all claims") == "admin"
    assert _classify_question("Show me all documents") == "admin"
    assert _classify_question("知识库里有什么") == "admin"
    assert _classify_question("有多少文档") == "admin"
