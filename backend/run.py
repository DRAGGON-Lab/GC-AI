from app import create_app
from app.utils.cleanup import start_cleanup_schedule
from dotenv import load_dotenv
import os

#load_dotenv()

def main():
    
    app = create_app()
    app.logger.info("Starting GC-AI development server...")
    start_cleanup_schedule()
    
    host = os.getenv('APP_HOST', '127.0.0.1')
    port = int(os.getenv('APP_PORT', 5000))
    app.run(host=host, port=port)
    
if __name__ == "__main__":
    main()
