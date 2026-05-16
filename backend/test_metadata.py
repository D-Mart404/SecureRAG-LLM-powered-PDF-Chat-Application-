from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate

# Create a doc with missing page
doc1 = Document(page_content="hello", metadata={})
doc1.metadata["chunk_number"] = 1
doc1.metadata["page"] = "?"

document_prompt = PromptTemplate.from_template("Source [Page {page}]:\n{page_content}")

try:
    print(document_prompt.format(page=doc1.metadata["page"], page_content=doc1.page_content))
    print("Direct format works")
except Exception as e:
    print("Direct error:", e)

from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.llms.fake import FakeListLLM

llm = FakeListLLM(responses=["test"])
prompt = ChatPromptTemplate.from_messages([("human", "{context}")])
chain = create_stuff_documents_chain(llm, prompt, document_prompt=document_prompt)

try:
    chain.invoke({"context": [doc1]})
    print("Chain works")
except Exception as e:
    print("Chain error:", e)
