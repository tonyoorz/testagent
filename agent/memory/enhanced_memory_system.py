"""
Enhanced Memory System - Three-tier memory architecture for AI Agent

Features:
1. Short-term memory: Current session conversation history
2. Working memory: Active context and temporary insights
3. Long-term memory: Persistent insights, patterns, and user preferences

Author: AI Assistant
Date: 2025-02-04
"""

import os
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import logging
from collections import defaultdict
import pandas as pd
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Insight:
    """Data class for storing insights"""
    id: Optional[int] = None
    insight_type: str = ""  # 'pattern', 'anomaly', 'recommendation', 'trend'
    content: str = ""
    confidence: float = 0.0
    data_snapshot: str = ""  # JSON string
    context_hash: str = ""  # Hash of data context for similarity matching
    created_at: Optional[datetime] = None
    used_count: int = 0
    last_used: Optional[datetime] = None
    tags: str = ""  # Comma-separated tags


@dataclass
class UserPreference:
    """Data class for user preferences"""
    user_id: str = "default"
    preference_key: str = ""
    preference_value: str = ""
    updated_at: Optional[datetime] = None


@dataclass
class InteractionRecord:
    """Data class for interaction history"""
    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    question: str = ""
    intents: str = ""  # JSON array
    tools_used: str = ""  # JSON array
    execution_time: float = 0.0
    success: bool = True
    user_feedback: Optional[int] = None  # 1-5 star rating
    error_message: str = ""
    insights_generated: int = 0


class EnhancedMemorySystem:
    """Three-tier memory architecture for intelligent agent"""
    
    def __init__(self, db_path: Optional[str] = None, user_id: str = "default"):
        """
        Initialize enhanced memory system
        
        Args:
            db_path: Path to SQLite database (if None, uses default)
            user_id: User identifier for personalization
        """
        if db_path is None:
            db_path = os.path.join(PROJECT_ROOT, 'database', 'agent_memory.db')
        
        # Ensure directory exists
        dirpath = os.path.dirname(db_path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        
        self.db_path = db_path
        self.user_id = user_id
        
        # Short-term memory: Current session
        self.short_term = []
        
        # Working memory: Active context
        self.working_memory = {
            'current_topic': None,
            'mentioned_entities': set(),
            'active_filters': {},
            'pending_questions': [],
            'last_analysis_results': None,
            'session_insights': []
        }
        
        # Long-term memory: Persistent database
        self._init_long_term_db()
        
        logger.info(f"Enhanced memory system initialized (DB: {db_path}, User: {user_id})")
    
    def _init_long_term_db(self):
        """Initialize long-term memory database"""
        conn = sqlite3.connect(self.db_path)
        
        # Insights table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insight_type TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                data_snapshot TEXT,
                context_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_count INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                tags TEXT,
                UNIQUE(context_hash, insight_type, content)
            )
        """)
        
        # User preferences table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT NOT NULL,
                preference_key TEXT NOT NULL,
                preference_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, preference_key)
            )
        """)
        
        # Interaction history table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interaction_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                question TEXT NOT NULL,
                intents TEXT,
                tools_used TEXT,
                execution_time REAL,
                success BOOLEAN,
                user_feedback INTEGER,
                error_message TEXT,
                insights_generated INTEGER DEFAULT 0
            )
        """)
        
        # Create indexes for performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(insight_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_insights_confidence ON insights(confidence)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_insights_hash ON insights(context_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_interaction_timestamp ON interaction_history(timestamp)")
        
        conn.commit()
        conn.close()
        
        logger.info("Long-term memory database initialized")
    
    # ========================================================================
    # Short-term Memory Operations
    # ========================================================================
    
    def add_to_short_term(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add message to short-term memory"""
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        self.short_term.append(message)
        
        # Keep only recent messages (configurable limit)
        max_short_term = int(os.getenv('MEMORY_SHORT_TERM_LIMIT', '50'))
        if len(self.short_term) > max_short_term:
            self.short_term = self.short_term[-max_short_term:]
    
    def get_short_term_context(self, last_n: int = 10) -> List[Dict]:
        """Get recent short-term memory"""
        return self.short_term[-last_n:] if self.short_term else []
    
    def clear_short_term(self):
        """Clear short-term memory"""
        self.short_term = []
        logger.info("Short-term memory cleared")
    
    # ========================================================================
    # Working Memory Operations
    # ========================================================================
    
    def update_working_memory(self, key: str, value: Any):
        """Update working memory"""
        self.working_memory[key] = value
    
    def get_working_memory(self, key: str, default: Any = None) -> Any:
        """Get value from working memory"""
        return self.working_memory.get(key, default)
    
    def add_mentioned_entity(self, entity: str):
        """Add entity to working memory"""
        if isinstance(self.working_memory['mentioned_entities'], set):
            self.working_memory['mentioned_entities'].add(entity)
    
    def get_mentioned_entities(self) -> set:
        """Get all mentioned entities"""
        return self.working_memory.get('mentioned_entities', set())
    
    def clear_working_memory(self):
        """Clear working memory"""
        self.working_memory = {
            'current_topic': None,
            'mentioned_entities': set(),
            'active_filters': {},
            'pending_questions': [],
            'last_analysis_results': None,
            'session_insights': []
        }
        logger.info("Working memory cleared")
    
    # ========================================================================
    # Long-term Memory Operations - Insights
    # ========================================================================
    
    def store_insight(self, insight_type: str, content: str, confidence: float,
                     data_snapshot: Optional[Dict] = None, tags: Optional[List[str]] = None) -> bool:
        """
        Store high-value insight to long-term memory
        
        Args:
            insight_type: Type of insight ('pattern', 'anomaly', 'recommendation', 'trend')
            content: Insight content
            confidence: Confidence score (0.0-1.0)
            data_snapshot: Snapshot of data context
            tags: List of tags for categorization
        
        Returns:
            True if stored successfully
        """
        # Only store high-confidence insights
        min_confidence = float(os.getenv('MEMORY_MIN_CONFIDENCE', '0.7'))
        if confidence < min_confidence:
            logger.debug(f"Insight confidence {confidence} below threshold {min_confidence}, not storing")
            return False
        
        # Generate context hash for deduplication
        context_hash = self._generate_context_hash(data_snapshot)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if similar insight already exists
            cursor.execute("""
                SELECT id, used_count FROM insights 
                WHERE context_hash = ? AND insight_type = ? AND content = ?
            """, (context_hash, insight_type, content))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing insight
                insight_id, used_count = existing
                cursor.execute("""
                    UPDATE insights 
                    SET used_count = ?, last_used = ?, confidence = MAX(confidence, ?)
                    WHERE id = ?
                """, (used_count + 1, datetime.now(), confidence, insight_id))
                logger.info(f"Updated existing insight #{insight_id}")
            else:
                # Insert new insight
                cursor.execute("""
                    INSERT INTO insights 
                    (insight_type, content, confidence, data_snapshot, context_hash, tags)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    insight_type,
                    content,
                    confidence,
                    json.dumps(data_snapshot) if data_snapshot else None,
                    context_hash,
                    ','.join(tags) if tags else ''
                ))
                logger.info(f"Stored new insight: {insight_type} (confidence: {confidence:.2f})")
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to store insight: {e}")
            return False
    
    def retrieve_relevant_insights(self, question: str, current_data_context: Optional[Dict] = None,
                                   insight_types: Optional[List[str]] = None,
                                   top_k: int = 5) -> List[Insight]:
        """
        Retrieve relevant insights from long-term memory
        
        Args:
            question: User question
            current_data_context: Current data context
            insight_types: Filter by insight types
            top_k: Number of insights to retrieve
        
        Returns:
            List of relevant insights
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Build query
            query = """
                SELECT id, insight_type, content, confidence, data_snapshot, 
                       context_hash, created_at, used_count, last_used, tags
                FROM insights
                WHERE confidence >= ?
            """
            params = [0.7]
            
            if insight_types:
                placeholders = ','.join(['?'] * len(insight_types))
                query += f" AND insight_type IN ({placeholders})"
                params.extend(insight_types)
            
            # Order by relevance (used_count and confidence)
            query += " ORDER BY (used_count * 0.3 + confidence * 0.7) DESC LIMIT ?"
            params.append(top_k)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            insights = []
            for row in rows:
                insight = Insight(
                    id=row[0],
                    insight_type=row[1],
                    content=row[2],
                    confidence=row[3],
                    data_snapshot=row[4] or "",
                    context_hash=row[5] or "",
                    created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    used_count=row[7],
                    last_used=datetime.fromisoformat(row[8]) if row[8] else None,
                    tags=row[9] or ""
                )
                insights.append(insight)
                
                # Update usage count
                cursor.execute("""
                    UPDATE insights 
                    SET used_count = used_count + 1, last_used = ?
                    WHERE id = ?
                """, (datetime.now(), insight.id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Retrieved {len(insights)} relevant insights")
            return insights
            
        except Exception as e:
            logger.error(f"Failed to retrieve insights: {e}")
            return []
    
    def get_insights_by_type(self, insight_type: str, limit: int = 10) -> List[Insight]:
        """Get insights by type"""
        return self.retrieve_relevant_insights("", insight_types=[insight_type], top_k=limit)
    
    def cleanup_old_insights(self, days: int = 90, min_used_count: int = 2):
        """
        Clean up old, rarely used insights
        
        Args:
            days: Delete insights older than this many days
            min_used_count: Keep insights with at least this many uses
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor.execute("""
                DELETE FROM insights
                WHERE created_at < ? AND used_count < ?
            """, (cutoff_date, min_used_count))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {deleted_count} old insights")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup insights: {e}")
            return 0
    
    # ========================================================================
    # Long-term Memory Operations - User Preferences
    # ========================================================================
    
    def learn_user_preference(self, preference_key: str, preference_value: Any):
        """
        Learn and store user preference
        
        Args:
            preference_key: Preference key (e.g., 'favorite_metrics', 'preferred_view')
            preference_value: Preference value
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Convert value to JSON if needed
            if not isinstance(preference_value, str):
                preference_value = json.dumps(preference_value)
            
            cursor.execute("""
                INSERT OR REPLACE INTO user_preferences 
                (user_id, preference_key, preference_value, updated_at)
                VALUES (?, ?, ?, ?)
            """, (self.user_id, preference_key, preference_value, datetime.now()))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Learned user preference: {preference_key}")
            
        except Exception as e:
            logger.error(f"Failed to learn user preference: {e}")
    
    def get_user_preference(self, preference_key: str, default: Any = None) -> Any:
        """Get user preference"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT preference_value FROM user_preferences
                WHERE user_id = ? AND preference_key = ?
            """, (self.user_id, preference_key))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                try:
                    return json.loads(row[0])
                except:
                    return row[0]
            
            return default
            
        except Exception as e:
            logger.error(f"Failed to get user preference: {e}")
            return default
    
    def get_all_user_preferences(self) -> Dict[str, Any]:
        """Get all user preferences"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT preference_key, preference_value FROM user_preferences
                WHERE user_id = ?
            """, (self.user_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            preferences = {}
            for key, value in rows:
                try:
                    preferences[key] = json.loads(value)
                except:
                    preferences[key] = value
            
            return preferences
            
        except Exception as e:
            logger.error(f"Failed to get user preferences: {e}")
            return {}
    
    # ========================================================================
    # Long-term Memory Operations - Interaction History
    # ========================================================================
    
    def log_interaction(self, question: str, intents: List[str], tools_used: List[str],
                       execution_time: float, success: bool, error_message: str = "",
                       insights_generated: int = 0):
        """Log interaction to history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO interaction_history
                (question, intents, tools_used, execution_time, success, error_message, insights_generated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                question,
                json.dumps(intents),
                json.dumps(tools_used),
                execution_time,
                success,
                error_message,
                insights_generated
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to log interaction: {e}")
    
    def get_interaction_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get interaction statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_interactions,
                    AVG(execution_time) as avg_execution_time,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
                    AVG(user_feedback) as avg_user_rating,
                    SUM(insights_generated) as total_insights
                FROM interaction_history
                WHERE timestamp > ?
            """, (cutoff_date,))
            
            row = cursor.fetchone()
            conn.close()
            
            return {
                'total_interactions': row[0] or 0,
                'avg_execution_time': row[1] or 0.0,
                'success_rate': row[2] or 0.0,
                'avg_user_rating': row[3] or 0.0,
                'total_insights': row[4] or 0,
                'period_days': days
            }
            
        except Exception as e:
            logger.error(f"Failed to get interaction stats: {e}")
            return {}
    
    def get_popular_questions(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most popular question patterns"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT question, COUNT(*) as count
                FROM interaction_history
                WHERE success = 1
                GROUP BY LOWER(question)
                ORDER BY count DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [(row[0], row[1]) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to get popular questions: {e}")
            return []
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def _generate_context_hash(self, data_snapshot: Optional[Dict]) -> str:
        """Generate hash for data context"""
        if not data_snapshot:
            return ""
        
        # Create a stable string representation
        context_str = json.dumps(data_snapshot, sort_keys=True)
        return hashlib.md5(context_str.encode()).hexdigest()
    
    def extract_insights_from_analysis(self, analysis_results: Dict, 
                                      confidence: float = 0.8) -> List[Dict]:
        """
        Extract insights from analysis results
        
        Args:
            analysis_results: Results from tool execution
            confidence: Confidence score for extracted insights
        
        Returns:
            List of extracted insights
        """
        insights = []
        
        # Extract patterns
        if 'patterns' in analysis_results:
            for pattern in analysis_results['patterns']:
                insights.append({
                    'type': 'pattern',
                    'content': pattern,
                    'confidence': confidence
                })
        
        # Extract anomalies
        if 'anomalies' in analysis_results:
            for anomaly in analysis_results['anomalies']:
                insights.append({
                    'type': 'anomaly',
                    'content': anomaly,
                    'confidence': confidence
                })
        
        # Extract recommendations
        if 'recommendations' in analysis_results:
            for rec in analysis_results['recommendations']:
                insights.append({
                    'type': 'recommendation',
                    'content': rec,
                    'confidence': confidence
                })
        
        return insights
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """Get summary of memory system state"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count insights
            cursor.execute("SELECT COUNT(*) FROM insights")
            insights_count = cursor.fetchone()[0]
            
            # Count preferences
            cursor.execute("SELECT COUNT(*) FROM user_preferences WHERE user_id = ?", (self.user_id,))
            preferences_count = cursor.fetchone()[0]
            
            # Count interactions
            cursor.execute("SELECT COUNT(*) FROM interaction_history")
            interactions_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'short_term_size': len(self.short_term),
                'working_memory_entities': len(self.working_memory.get('mentioned_entities', set())),
                'long_term_insights': insights_count,
                'user_preferences': preferences_count,
                'total_interactions': interactions_count,
                'db_path': self.db_path,
                'user_id': self.user_id
            }
            
        except Exception as e:
            logger.error(f"Failed to get memory summary: {e}")
            return {}


# Factory function
def create_memory_system(db_path: Optional[str] = None, user_id: str = "default") -> EnhancedMemorySystem:
    """Create enhanced memory system instance"""
    return EnhancedMemorySystem(db_path, user_id)


# Test code
if __name__ == "__main__":
    print("Enhanced Memory System Test")
    print("=" * 50)
    
    # Create memory system
    memory = create_memory_system(db_path="test_memory.db", user_id="test_user")
    
    # Test 1: Short-term memory
    print("\n1. Testing short-term memory:")
    memory.add_to_short_term("user", "What is the defect trend?")
    memory.add_to_short_term("assistant", "The defect trend is increasing.")
    print(f"Short-term messages: {len(memory.get_short_term_context())}")
    
    # Test 2: Working memory
    print("\n2. Testing working memory:")
    memory.update_working_memory('current_topic', 'defect_trend')
    memory.add_mentioned_entity('G01')
    memory.add_mentioned_entity('G20')
    print(f"Current topic: {memory.get_working_memory('current_topic')}")
    print(f"Mentioned entities: {memory.get_mentioned_entities()}")
    
    # Test 3: Store insights
    print("\n3. Testing insight storage:")
    memory.store_insight(
        insight_type='pattern',
        content='G01 project has consistently high defect rate',
        confidence=0.85,
        data_snapshot={'project': 'G01', 'defect_count': 150},
        tags=['G01', 'high_defect_rate']
    )
    memory.store_insight(
        insight_type='anomaly',
        content='Critical defects spiked in week 5',
        confidence=0.92,
        data_snapshot={'week': 5, 'critical_count': 25},
        tags=['critical', 'spike']
    )
    print("✅ Insights stored")
    
    # Test 4: Retrieve insights
    print("\n4. Testing insight retrieval:")
    insights = memory.retrieve_relevant_insights("defect patterns", top_k=5)
    print(f"Retrieved {len(insights)} insights:")
    for insight in insights:
        print(f"  - [{insight.insight_type}] {insight.content} (confidence: {insight.confidence:.2f})")
    
    # Test 5: User preferences
    print("\n5. Testing user preferences:")
    memory.learn_user_preference('favorite_metrics', ['defect_count', 'critical_rate'])
    memory.learn_user_preference('preferred_view', 'trend_chart')
    prefs = memory.get_all_user_preferences()
    print(f"User preferences: {prefs}")
    
    # Test 6: Interaction logging
    print("\n6. Testing interaction logging:")
    memory.log_interaction(
        question="Show me defect trends",
        intents=['trend', 'summary'],
        tools_used=['time_series_counts', 'top_counts'],
        execution_time=1.5,
        success=True,
        insights_generated=2
    )
    stats = memory.get_interaction_stats(days=7)
    print(f"Interaction stats: {stats}")
    
    # Test 7: Memory summary
    print("\n7. Memory system summary:")
    summary = memory.get_memory_summary()
    for key, value in summary.items():
        print(f"  - {key}: {value}")
    
    print("\n✅ All tests completed!")
    
    # Cleanup test database
    import os
    if os.path.exists("test_memory.db"):
        os.remove("test_memory.db")
        print("Test database cleaned up")
