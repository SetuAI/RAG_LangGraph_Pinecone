import os
from pinecone import Pinecone,ServerlessSpec
from langchain_pinecone import PineconeVectorStore
# from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings

# for text splitter
from langchain_text_splitters import RecursiveCharacterTextSplitter

# import PINECONE_API_KEY and other configurations
from config import PINECONE_API_KEY
os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY

# Pinecone index set up : https://app.pinecone.io/organizations/-NvankU832R3Eg6IXOo3/projects/feff407b-ff5a-472a-a02a-d576882ed484/indexes/rag-test001/browser
# Initialize Pinecone Client
pc = Pinecone(api_key=PINECONE_API_KEY)
#index = pc.Index("rag-test-001")

# define embedding model
#embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

# define Pinecone index
INDEX_NAME = "rag-test002"

# retriever function 
def get_retriever():
    '''
    Initialises and returns a Pinecone Vector Store retriever.
    Ensure , the index exists , else create it.
    '''
    if INDEX_NAME not in pc.list_indexes().names():
        print("Creating Index...")
        pc.create_index(INDEX_NAME, 
                        dimension=1024, 
                        metric="cosine",
                        spec = ServerlessSpec(cloud ="aws", region="us-east-1"))
        print("Created Pinecone Index...........")
        
        # get the pinecone vector store
    vector_store = PineconeVectorStore(index_name=INDEX_NAME,embedding = embeddings)
    return vector_store.as_retriever()

# upload documents to vector store

def add_document(text_content: str):
    '''
    Will receive text content in form of string format.
    Adds a single text document to the Pinecone Vector Store.
    Splits the text into chunks before embedding and upserting.
    '''
    
    if not text_content:
        raise ValueError("Document content cannot be empty.")
    
    # after uploading, split the document
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000,
                                                   chunk_overlap=200,
                                                   add_start_index=True)
    
    # Create document objects from the text content (to store the raw text)
    documents = text_splitter.create_documents([text_content])
    
    print("Splitting the document into chunks...")
    print(f"Splitting document into {len(documents)} chunks for indexing...")
    
     # Get the vectorstore instance (not the retriever) to add documents
    vectorstore = PineconeVectorStore(index_name=INDEX_NAME, embedding=embeddings)
    
    
    # Add documents to the vector store
    vectorstore.add_documents(documents)
    print(f"Successfully added {len(documents)} chunks to Pinecone index '{INDEX_NAME}'.")

