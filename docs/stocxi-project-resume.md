# Stocxi — Project Resume

## Full-Stack AI Finance Product

Stocxi is an AI-powered Indian stock analysis platform for retail investors.
It combines verified market data, financial statements, technical indicators,
news, announcements, knowledge graphs, and AI-generated analysis into one
transparent research workflow.

## One-Line Pitch

Built a production-grade stock intelligence platform that turns NSE/BSE market
data into citation-backed, beginner-friendly AI analysis.

## Tech Stack

| Layer | Stack |
|---|---|
| Frontend | Next.js 16, React, TypeScript |
| Backend | FastAPI, Python |
| Data | NSE, BSE, Screener, yfinance fallback, RSS |
| AI | Gemini / OpenRouter |
| Cache | Redis / Upstash |
| Visualization | Three.js knowledge graph |
| Validation | Pydantic schemas, verifier agent, audit logs |

## What It Does

- Lets users search Indian stocks.
- Shows live overview, price, ratios, fundamentals, and technicals.
- Fetches financial statements and shareholding data.
- Aggregates announcements and approved news sources.
- Builds typed data nodes for every important signal.
- Creates a knowledge graph of relationships and contradictions.
- Runs AI analysis with strict citation requirements.
- Strips unsupported claims before returning output.
- Shows signals in favor and against.
- Keeps mandatory financial disclaimers visible.

## Architecture Highlights

- Multi-agent backend pipeline.
- Parallel data fetching with time budgets.
- Source waterfall by reliability.
- Pydantic messages between agents.
- Sanitized news before any LLM prompt.
- Anonymized stock names during reasoning.
- Deterministic output formatting.
- Redis cache for faster repeated analysis.
- Audit logs for traceability.

## Resume Bullets

- Built Stocxi, an AI-powered stock analysis platform for Indian retail investors.
- Engineered FastAPI services that merge NSE, BSE, Screener, news, and technical data.
- Designed a multi-agent analysis pipeline with deterministic verification and auditability.
- Developed a premium Next.js interface for stock research, charts, filings, and AI reports.
- Implemented knowledge graph visualization to explain signal relationships and contradictions.
- Added source priority, confidence scoring, cache keys, and graceful degradation.
- Shaped AI output for beginner investors while preserving risk disclosures.

## Impact Metrics

| Metric | Value |
|---|---:|
| Technical indicators | 17 per stock |
| Data domains | 5 parallel domains |
| Data agents | Technical, Fundamental, News, Announcement, Context |
| Pipeline budget | 60 seconds |
| Data source confidence | L1 to L4 priority model |

## Interview Summary

Stocxi shows end-to-end product engineering. It combines frontend design,
backend architecture, financial data ingestion, LLM orchestration, caching,
knowledge graphs, and verification. The product is built around trust:
approved sources, typed schemas, sanitized prompts, cited claims, and visible
disclaimers.

