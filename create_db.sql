-- Create database and user for e-learning platform
-- Run with: psql -U postgres -f create_db.sql

-- Create database (will fail if exists, that's OK)
CREATE DATABASE elearning_db;

-- Connect to the new database
\c elearning_db

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON DATABASE elearning_db TO postgres;

\q
