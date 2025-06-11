import os
import json
import google.generativeai as genai
import streamlit as st
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime
import re

class AIAnalyzer:
    """
    AI-powered analyzer using Google Gemini for root cause analysis and insights.
    Processes Jira ticket data to extract patterns, categorize issues, and generate actionable insights.
    """
    
    def __init__(self):
        """Initialize AI analyzer with Google Gemini configuration."""
        self.api_key = os.getenv('GOOGLE_API_KEY')
        
        if not self.api_key:
            st.warning("Google AI API key not configured")
            return
        
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            self._test_connection()
        except Exception as e:
            st.error(f"Error initializing AI analyzer: {str(e)}")
            self.model = None
    
    def _test_connection(self) -> bool:
        """Test connection to Google Gemini API."""
        try:
            response = self.model.generate_content("Test connection")
            return True
        except Exception as e:
            st.warning(f"AI service connection test failed: {str(e)}")
            return False
    
    def analyze_individual_tickets(self, tickets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze individual tickets for root cause analysis.
        
        Args:
            tickets: List of ticket dictionaries
            
        Returns:
            List of analysis results for each ticket
        """
        if not self.model:
            st.error("AI model not available")
            return []
        
        results = []
        
        for ticket in tickets:
            try:
                analysis = self._analyze_single_ticket(ticket)
                if analysis:
                    results.append(analysis)
            except Exception as e:
                st.warning(f"Error analyzing ticket {ticket.get('ticket_id', 'Unknown')}: {str(e)}")
                continue
        
        return results
    
    def _analyze_single_ticket(self, ticket: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Analyze a single ticket for root cause and categorization.
        
        Args:
            ticket: Ticket dictionary with details
            
        Returns:
            Analysis result dictionary
        """
        try:
            # Prepare ticket context
            context = self._prepare_ticket_context(ticket)
            
            # Generate analysis prompt
            prompt = self._create_analysis_prompt(context)
            
            # Get AI response
            response = self.model.generate_content(prompt)
            
            # Parse response
            analysis_result = self._parse_analysis_response(response.text, ticket)
            
            return analysis_result
            
        except Exception as e:
            st.error(f"Error in single ticket analysis: {str(e)}")
            return None
    
    def _prepare_ticket_context(self, ticket: Dict[str, Any]) -> str:
        """
        Prepare ticket context for AI analysis.
        
        Args:
            ticket: Ticket dictionary
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        # Basic information
        context_parts.append(f"Ticket ID: {ticket.get('ticket_id', 'Unknown')}")
        context_parts.append(f"Summary: {ticket.get('summary', 'No summary')}")
        context_parts.append(f"Status: {ticket.get('status', 'Unknown')}")
        context_parts.append(f"Priority: {ticket.get('priority', 'Unknown')}")
        context_parts.append(f"Issue Type: {ticket.get('issue_type', 'Unknown')}")
        
        # Description
        description = ticket.get('description', '')
        if description:
            context_parts.append(f"Description: {description[:1000]}...")  # Limit length
        
        # Comments
        comments = ticket.get('comments', [])
        if comments:
            context_parts.append("Recent Comments:")
            for i, comment in enumerate(comments[-3:]):  # Last 3 comments
                context_parts.append(f"Comment {i+1}: {comment.get('body', '')[:500]}...")
        
        # Status history
        status_history = ticket.get('status_history', [])
        if status_history:
            context_parts.append("Status Changes:")
            for change in status_history[-5:]:  # Last 5 changes
                context_parts.append(
                    f"From {change.get('from_status', 'Unknown')} to {change.get('to_status', 'Unknown')} "
                    f"on {change.get('changed_date', 'Unknown date')}"
                )
        
        # Resolution info
        if ticket.get('resolution'):
            context_parts.append(f"Resolution: {ticket['resolution']}")
        
        if ticket.get('resolution_time_hours'):
            context_parts.append(f"Resolution Time: {ticket['resolution_time_hours']:.1f} hours")
        
        return "\n".join(context_parts)
    
    def _create_analysis_prompt(self, context: str) -> str:
        """
        Create structured prompt for AI analysis.
        
        Args:
            context: Ticket context
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""
You are an expert support operations analyst for Razorpay, a fintech company. Analyze the following support ticket and provide a comprehensive root cause analysis.

TICKET CONTEXT:
{context}

Please provide your analysis in the following JSON format:

{{
    "category": "Primary issue category (e.g., 'Technical Integration', 'Payment Processing', 'Account Management', 'API Issues', 'Documentation', 'Configuration')",
    "subcategory": "Specific subcategory within the main category",
    "root_cause": "Detailed root cause analysis - what actually caused this issue",
    "primary_symptom": "Main symptom or problem reported by the user",
    "actions_taken": "Summary of actions taken to resolve the issue",
    "resolution_effectiveness": "Score from 1-5 (5 being most effective) based on how well the issue was resolved",
    "business_impact": "Assessment of business impact: Low/Medium/High",
    "prevention_suggestions": "Specific suggestions to prevent similar issues",
    "knowledge_gap": "Any knowledge gaps identified in support process",
    "escalation_reason": "If escalated, what was the primary reason",
    "customer_sentiment": "Perceived customer sentiment: Positive/Neutral/Negative",
    "technical_complexity": "Technical complexity level: Low/Medium/High",
    "time_to_resolution_assessment": "Was resolution time appropriate: Yes/No/Could be better"
}}

Focus on:
1. Identifying the true root cause, not just symptoms
2. Understanding the customer's perspective and impact
3. Recognizing patterns that could help prevent future issues
4. Assessing the effectiveness of the support process
5. Providing actionable insights for improvement

Be specific and practical in your analysis. Use your knowledge of fintech and payment processing to provide contextual insights.
"""
        
        return prompt
    
    def _parse_analysis_response(self, response_text: str, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse AI response and extract structured analysis.
        
        Args:
            response_text: AI response text
            ticket: Original ticket data
            
        Returns:
            Parsed analysis dictionary
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                analysis = json.loads(json_str)
            else:
                # Fallback: parse structured text
                analysis = self._parse_structured_text(response_text)
            
            # Add metadata
            analysis['ticket_id'] = ticket.get('ticket_id')
            analysis['analysis_timestamp'] = datetime.now().isoformat()
            analysis['original_summary'] = ticket.get('summary', '')
            analysis['original_status'] = ticket.get('status', '')
            analysis['original_priority'] = ticket.get('priority', '')
            
            return analysis
            
        except Exception as e:
            st.warning(f"Error parsing AI response for ticket {ticket.get('ticket_id')}: {str(e)}")
            
            # Return basic analysis
            return {
                'ticket_id': ticket.get('ticket_id'),
                'category': 'Analysis Failed',
                'root_cause': 'Unable to analyze due to parsing error',
                'analysis_timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
    
    def _parse_structured_text(self, text: str) -> Dict[str, Any]:
        """
        Parse structured text response when JSON parsing fails.
        
        Args:
            text: Response text
            
        Returns:
            Parsed analysis dictionary
        """
        analysis = {}
        
        # Define field patterns
        patterns = {
            'category': r'category["\s]*:[\s]*["\']?([^"\'\n]+)',
            'subcategory': r'subcategory["\s]*:[\s]*["\']?([^"\'\n]+)',
            'root_cause': r'root_cause["\s]*:[\s]*["\']?([^"\'\n]+)',
            'actions_taken': r'actions_taken["\s]*:[\s]*["\']?([^"\'\n]+)',
            'business_impact': r'business_impact["\s]*:[\s]*["\']?([^"\'\n]+)',
            'resolution_effectiveness': r'resolution_effectiveness["\s]*:[\s]*["\']?([^"\'\n]+)',
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                analysis[field] = match.group(1).strip().strip('"\'')
            else:
                analysis[field] = 'Not specified'
        
        return analysis
    
    def analyze_aggregated_patterns(self, tickets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze patterns across multiple tickets for aggregated insights.
        
        Args:
            tickets: List of ticket dictionaries
            
        Returns:
            List of pattern analysis results
        """
        if not self.model:
            st.error("AI model not available")
            return []
        
        try:
            # Group tickets by categories for pattern analysis
            patterns = self._identify_common_patterns(tickets)
            
            # Generate insights for each pattern
            pattern_analyses = []
            
            for pattern in patterns:
                analysis = self._analyze_pattern(pattern, tickets)
                if analysis:
                    pattern_analyses.append(analysis)
            
            return pattern_analyses
            
        except Exception as e:
            st.error(f"Error in aggregated pattern analysis: {str(e)}")
            return []
    
    def _identify_common_patterns(self, tickets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify common patterns across tickets.
        
        Args:
            tickets: List of tickets
            
        Returns:
            List of identified patterns
        """
        patterns = []
        
        # Group by issue type and status
        df = pd.DataFrame(tickets)
        
        # Pattern 1: Issue type frequency
        issue_type_counts = df['issue_type'].value_counts()
        for issue_type, count in issue_type_counts.head(5).items():
            if count >= 2:  # At least 2 occurrences
                pattern_tickets = df[df['issue_type'] == issue_type].to_dict('records')
                patterns.append({
                    'type': 'issue_type_pattern',
                    'pattern_name': f"Frequent {issue_type} Issues",
                    'count': count,
                    'tickets': pattern_tickets
                })
        
        # Pattern 2: Status progression patterns
        status_patterns = df['status'].value_counts()
        for status, count in status_patterns.items():
            if count >= 3:  # At least 3 tickets with same status
                pattern_tickets = df[df['status'] == status].to_dict('records')
                patterns.append({
                    'type': 'status_pattern',
                    'pattern_name': f"Tickets Stuck in {status}",
                    'count': count,
                    'tickets': pattern_tickets
                })
        
        # Pattern 3: High resolution time
        if 'resolution_time_hours' in df.columns:
            high_resolution_tickets = df[df['resolution_time_hours'] > 48]  # More than 2 days
            if len(high_resolution_tickets) >= 2:
                patterns.append({
                    'type': 'resolution_time_pattern',
                    'pattern_name': "Long Resolution Time Issues",
                    'count': len(high_resolution_tickets),
                    'tickets': high_resolution_tickets.to_dict('records')
                })
        
        return patterns
    
    def _analyze_pattern(self, pattern: Dict[str, Any], all_tickets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Analyze a specific pattern for insights.
        
        Args:
            pattern: Pattern dictionary
            all_tickets: All tickets for context
            
        Returns:
            Pattern analysis result
        """
        try:
            pattern_tickets = pattern['tickets']
            
            # Create context for pattern analysis
            context = self._create_pattern_context(pattern, pattern_tickets)
            
            # Generate pattern analysis prompt
            prompt = f"""
You are analyzing support ticket patterns for Razorpay. Analyze the following pattern and provide insights.

PATTERN CONTEXT:
{context}

Provide analysis in JSON format:

{{
    "pattern_type": "{pattern['type']}",
    "pattern_name": "{pattern['pattern_name']}",
    "root_causes": ["List of common root causes across these tickets"],
    "impact_assessment": "Overall business impact of this pattern",
    "trend_analysis": "Is this pattern increasing, decreasing, or stable",
    "prevention_strategies": ["Specific strategies to prevent this pattern"],
    "process_improvements": ["Process improvements to address this pattern"],
    "training_needs": ["Any training needs identified"],
    "priority_level": "High/Medium/Low priority for addressing",
    "estimated_effort": "Estimated effort to resolve: Low/Medium/High",
    "success_metrics": ["How to measure success in addressing this pattern"]
}}

Focus on actionable insights that can help improve support operations.
"""
            
            response = self.model.generate_content(prompt)
            
            # Parse response
            analysis = self._parse_analysis_response(response.text, {'ticket_id': 'pattern_analysis'})
            
            # Add pattern metadata
            analysis['pattern_ticket_count'] = pattern['count']
            analysis['analysis_timestamp'] = datetime.now().isoformat()
            
            return analysis
            
        except Exception as e:
            st.warning(f"Error analyzing pattern {pattern.get('pattern_name', 'Unknown')}: {str(e)}")
            return None
    
    def _create_pattern_context(self, pattern: Dict[str, Any], tickets: List[Dict[str, Any]]) -> str:
        """
        Create context for pattern analysis.
        
        Args:
            pattern: Pattern information
            tickets: Tickets in the pattern
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        context_parts.append(f"Pattern Type: {pattern['type']}")
        context_parts.append(f"Pattern Name: {pattern['pattern_name']}")
        context_parts.append(f"Ticket Count: {pattern['count']}")
        
        context_parts.append("\nTickets in Pattern:")
        
        for i, ticket in enumerate(tickets[:5]):  # Limit to first 5
            context_parts.append(f"\nTicket {i+1}:")
            context_parts.append(f"  ID: {ticket.get('ticket_id', 'Unknown')}")
            context_parts.append(f"  Summary: {ticket.get('summary', 'No summary')}")
            context_parts.append(f"  Status: {ticket.get('status', 'Unknown')}")
            context_parts.append(f"  Priority: {ticket.get('priority', 'Unknown')}")
            
            if ticket.get('resolution_time_hours'):
                context_parts.append(f"  Resolution Time: {ticket['resolution_time_hours']:.1f} hours")
        
        return "\n".join(context_parts)
    
    def identify_patterns(self, tickets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify patterns and generate insights across tickets.
        
        Args:
            tickets: List of ticket dictionaries
            
        Returns:
            List of identified patterns and insights
        """
        if not tickets:
            return []
        
        # Combine individual analysis with pattern recognition
        individual_analyses = self.analyze_individual_tickets(tickets)
        pattern_analyses = self.analyze_aggregated_patterns(tickets)
        
        # Combine results
        all_analyses = individual_analyses + pattern_analyses
        
        return all_analyses
    
    def extract_root_causes(self, analysis_results: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Extract and count root causes from analysis results.
        
        Args:
            analysis_results: List of analysis results
            
        Returns:
            Dictionary with root cause counts
        """
        root_causes = {}
        
        for result in analysis_results:
            category = result.get('category', 'Unknown')
            root_cause = result.get('root_cause', 'Unknown')
            
            # Use category as primary grouping
            if category in root_causes:
                root_causes[category] += 1
            else:
                root_causes[category] = 1
        
        return root_causes
    
    def generate_executive_summary(self, analysis_results: List[Dict[str, Any]]) -> str:
        """
        Generate executive summary from analysis results.
        
        Args:
            analysis_results: List of analysis results
            
        Returns:
            Executive summary text
        """
        try:
            if not analysis_results:
                return "No analysis results available for summary."
            
            # Extract key metrics
            total_tickets = len(analysis_results)
            categories = {}
            high_impact_issues = 0
            
            for result in analysis_results:
                category = result.get('category', 'Unknown')
                categories[category] = categories.get(category, 0) + 1
                
                if result.get('business_impact', '').lower() == 'high':
                    high_impact_issues += 1
            
            # Create summary
            summary_parts = []
            summary_parts.append(f"Analysis of {total_tickets} support tickets reveals:")
            
            if categories:
                top_category = max(categories, key=categories.get)
                summary_parts.append(f"• Primary issue category: {top_category} ({categories[top_category]} tickets)")
            
            if high_impact_issues > 0:
                impact_percentage = (high_impact_issues / total_tickets) * 100
                summary_parts.append(f"• High business impact issues: {high_impact_issues} ({impact_percentage:.1f}%)")
            
            summary_parts.append("• Recommended actions: Focus on process improvements and preventive measures")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            st.error(f"Error generating executive summary: {str(e)}")
            return "Unable to generate executive summary."
