# AI Construction Agent - MVP

AI-powered construction quotation generation system that uses AI agents to extract project requirements and generate accurate cost estimates.

## Project Structure

```
ai-agent/
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── agents/       # AI agents (Data Collector, Cost Calculator)
│   │   ├── api/          # API endpoints
│   │   ├── core/         # Core configuration and database
│   │   ├── models/       # Database models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/    # Services (PDF generation)
│   │   └── utils/       # Utility functions
│   ├── alembic/          # Database migrations
│   └── requirements.txt
├── frontend/             # Next.js frontend
│   └── app/              # Next.js app directory
├── docker-compose.yml     # Docker setup
└── README.md
```

## Prerequisites

- Docker and Docker Compose (recommended)
- OR Node.js 18+ and Python 3.11+ for local development
- OpenAI API key OR Anthropic API key (for LLM functionality)

## Quick Start with Docker

1. **Clone and navigate to the project:**
   ```bash
   cd ai-agent
   ```

2. **Set up environment variables:**
   ```bash
   # Backend
   cd backend
   cp .env.example .env
   # Edit .env and add your LLM API key (RUNPOD_API_KEY or ANTHROPIC_API_KEY)
   
   # Frontend
   cd ../frontend
   cp .env.example .env
   ```

3. **Start the services:**
   ```bash
   cd ..
   docker-compose up -d
   ```

4. **Run database migrations:**
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

5. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Local Development Setup

### Backend

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and configure:
   - `DATABASE_URL`: PostgreSQL connection string
   - `SECRET_KEY`: Random secret key for JWT
   - `RUNPOD_API_KEY` or `ANTHROPIC_API_KEY`: Your LLM API key
   - `LLM_PROVIDER`: "openai" or "anthropic"
   - `LLM_MODEL`: Model name (e.g., "gpt-4-turbo-preview" or "claude-3-5-sonnet-20241022")

5. **Set up PostgreSQL database:**
   ```bash
   # Using Docker
   docker run -d --name postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=construction_ai -p 5432:5432 postgres:15
   ```

6. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

7. **Start the server:**
   ```bash
   uvicorn app.main:app --reload
   ```

### Frontend

1. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env`:
   - `NEXT_PUBLIC_API_URL`: Backend API URL (default: http://localhost:8000)

4. **Start the development server:**
   ```bash
   npm run dev
   ```

## API Endpoints

### Create Quotation
```
POST /api/v1/quotations
```

**Request Body:**
```json
{
  "project_description": "2000 sq ft office renovation in downtown Chicago, modern finishes, 8-week timeline",
  "location": "123 Main St, Chicago, IL",
  "zip_code": "60601",
  "project_type": "commercial",
  "timeline": "8 weeks"
}
```

**Response:**
```json
{
  "id": "quot-abc123def456",
  "project_description": "...",
  "status": "pending",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Get Quotation
```
GET /api/v1/quotations/{quotation_id}?include_data=true
```

### Get Quotation Status
```
GET /api/v1/quotations/{quotation_id}/status
```

**Response:**
```json
{
  "quotation_id": "quot-abc123def456",
  "status": "cost_calculation",
  "current_stage": "cost_calculation",
  "progress": 70,
  "estimated_completion": "2025-01-01T00:05:00Z",
  "last_update": "2025-01-01T00:03:00Z"
}
```

### Download Quotation PDF
```
GET /api/v1/quotations/{quotation_id}/download
```

### List Quotations
```
GET /api/v1/quotations?skip=0&limit=100
```

## How It Works

1. **User Input**: User enters project description via web form (supports Arabic and English)
2. **Language Detection**: System automatically detects language (Arabic/English/Mixed)
3. **Data Collector Agent**: Extracts key parameters (project type, size, location, requirements) using LLM
4. **Cost Calculator Agent**: Calculates costs based on extracted data using mock pricing data
5. **PDF Generation**: Generates professional quotation document
6. **Download**: User can download the quotation PDF

## Multilingual Support (Arabic & English)

The system fully supports **Arabic** and **English** languages:
- Automatic language detection
- Bilingual prompts for LLM
- RTL (Right-to-Left) text support in UI
- Mixed language input handling
- Responses in the same language as input

## Egypt Market Configuration

The system is configured for the **Egyptian market**:
- **Currency**: Egyptian Pounds (EGP)
- **Measurement Units**: Square meters (sqm) - primary, with square feet support
- **Regional Pricing**: Egypt-specific rates for major cities (Cairo, Alexandria, Giza, New Cairo, etc.)
- **Labor Rates**: Egypt market rates (EGP per hour)
- **Material Costs**: Egypt market prices (EGP per sqm)
- **Location Detection**: Automatic detection of Egyptian cities/governorates

See [AGENT_USAGE_GUIDE.md](AGENT_USAGE_GUIDE.md) for detailed usage examples.
See [EGYPT_CONFIGURATION.md](EGYPT_CONFIGURATION.md) for Egypt-specific configuration details.

## Database Schema

### quotations
- `id` (String, Primary Key) - Unique quotation identifier
- `project_description` (String) - User's project description
- `location` (String, Optional) - Project location
- `zip_code` (String, Optional) - Zip code for regional pricing
- `project_type` (Enum, Optional) - residential/commercial/renovation/new_construction
- `timeline` (String, Optional) - Project timeline
- `status` (Enum) - pending/processing/data_collection/cost_calculation/completed/failed
- `created_at` (DateTime)
- `updated_at` (DateTime)

### quotation_data
- `id` (Integer, Primary Key)
- `quotation_id` (String, Foreign Key) - References quotations.id
- `extracted_data` (JSON) - Data extracted by Data Collector agent
- `confidence_score` (Float) - Confidence in extracted data (0.0-1.0)
- `cost_breakdown` (JSON) - Detailed cost breakdown
- `total_cost` (Float) - Total estimated cost
- `created_at` (DateTime)
- `updated_at` (DateTime)

## Development Status

### ✅ Phase 1: Foundation & Core Infrastructure
- [x] Project structure setup
- [x] FastAPI backend with basic routing
- [x] Next.js frontend
- [x] PostgreSQL database schema
- [x] Docker setup
- [x] Basic web interface for project input
- [x] API endpoints for quotation creation and status

### ✅ Phase 2: AI Agent Orchestration
- [x] AI agent framework setup (LangChain)
- [x] Data Collector agent (extracts project parameters)
- [x] Cost Calculator agent (calculates costs)
- [x] Agent orchestration (sequential execution)
- [x] Background task processing
- [x] Agent state tracking

### ✅ Phase 3: Cost Calculation & Quotation Generation
- [x] Enhanced cost calculation with mock data
- [x] PDF quotation document generation
- [x] Cost breakdown visualization in UI
- [x] Download quotation endpoint

### ✅ Phase 4: Polish & Basic Integrations
- [x] User experience improvements
- [x] Error handling and validation
- [x] Input validation (project description, zip code, project type)
- [x] Global exception handling
- [x] Logging setup
- [x] API documentation (OpenAPI/Swagger)

## Testing

### Manual Testing

1. **Create a quotation:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/quotations \
     -H "Content-Type: application/json" \
     -d '{
       "project_description": "2000 sq ft office renovation in downtown Chicago, modern finishes, 8-week timeline",
       "location": "123 Main St, Chicago, IL",
       "zip_code": "60601",
       "project_type": "commercial"
     }'
   ```

2. **Check status:**
   ```bash
   curl http://localhost:8000/api/v1/quotations/{quotation_id}/status
   ```

3. **Download PDF:**
   ```bash
   curl http://localhost:8000/api/v1/quotations/{quotation_id}/download -o quotation.pdf
   ```

## Configuration

### Environment Variables (Backend)

- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: Secret key for JWT tokens
- `LLM_PROVIDER`: "openai" or "anthropic"
- `RUNPOD_API_KEY`: OpenAI API key (if using OpenAI)
- `ANTHROPIC_API_KEY`: Anthropic API key (if using Anthropic)
- `LLM_MODEL`: Model name (e.g., "gpt-4-turbo-preview")
- `CORS_ORIGINS`: Comma-separated list of allowed origins
- `ENVIRONMENT`: "development" or "production"

### Environment Variables (Frontend)

- `NEXT_PUBLIC_API_URL`: Backend API URL

## Troubleshooting

### Database Connection Issues
- Ensure PostgreSQL is running
- Check `DATABASE_URL` in `.env`
- Verify database exists: `docker-compose exec db psql -U postgres -l`

### LLM API Errors
- Verify API key is set correctly
- Check API key has sufficient credits
- Ensure `LLM_PROVIDER` matches the API key type

### Frontend Not Connecting to Backend
- Check `NEXT_PUBLIC_API_URL` in frontend `.env`
- Verify backend is running on the correct port
- Check CORS settings in backend

## Next Steps

- Add more sophisticated cost calculation with real supplier APIs
- Implement Research Agent for building codes and market data
- Add Plan Generator Agent for timelines and resource planning
- Implement user authentication
- Add WebSocket support for real-time updates
- Expand test coverage

## License

MIT
