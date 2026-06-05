#!/usr/bin/env python3
"""
Response Format Validator for Event Tracking

Use this to validate that your FastAPI agent service returns
the correct response structure for proper Temporal activity grouping.

Usage:
    python validate_response.py <response.json>
    
Or import and use programmatically:
    from validate_response import validate_response
    is_valid, errors = validate_response(response_dict)
"""

import json
import sys
from typing import Any


def validate_response(response: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate FastAPI agent response structure.
    
    Returns:
        (is_valid, errors) tuple
        - is_valid: True if response is valid
        - errors: List of validation error messages (empty if valid)
    """
    errors = []
    
    # Check body exists
    if "body" not in response:
        errors.append("Missing 'body' field in response")
        return False, errors
    
    body = response["body"]
    if not isinstance(body, dict):
        errors.append("'body' must be a dict")
        return False, errors
    
    # tool_calls is optional but if present must be valid
    if "tool_calls" not in body:
        # No tool calls is valid
        return True, []
    
    tool_calls = body["tool_calls"]
    
    # Check tool_calls is a list
    if not isinstance(tool_calls, list):
        errors.append("'tool_calls' must be a list")
        return False, errors
    
    # Empty list is valid
    if len(tool_calls) == 0:
        return True, []
    
    # Validate each tool call event
    required_fields = {"event_type", "tool_name", "status"}
    
    for idx, event in enumerate(tool_calls):
        if not isinstance(event, dict):
            errors.append(f"tool_calls[{idx}]: Event must be a dict")
            continue
        
        # Check required fields
        missing = required_fields - set(event.keys())
        if missing:
            errors.append(f"tool_calls[{idx}]: Missing fields: {missing}")
        
        # Validate event_type
        if event.get("event_type") != "tool_call":
            errors.append(
                f"tool_calls[{idx}]: event_type must be 'tool_call', "
                f"got '{event.get('event_type')}'"
            )
        
        # Validate status
        valid_statuses = {"started", "succeeded", "failed"}
        status = event.get("status")
        if status not in valid_statuses:
            errors.append(
                f"tool_calls[{idx}]: status must be one of {valid_statuses}, "
                f"got '{status}'"
            )
        
        # Validate status-specific fields
        if status == "started":
            if "input" not in event:
                errors.append(
                    f"tool_calls[{idx}]: 'started' event must have 'input' field"
                )
        elif status == "succeeded":
            if "output" not in event:
                errors.append(
                    f"tool_calls[{idx}]: 'succeeded' event must have 'output' field"
                )
        elif status == "failed":
            if "error" not in event:
                errors.append(
                    f"tool_calls[{idx}]: 'failed' event must have 'error' field"
                )
    
    # Check pairing: every started should have a succeeded/failed
    tool_tracking = {}
    for event in tool_calls:
        if not isinstance(event, dict):
            continue
        
        tool_name = event.get("tool_name")
        status = event.get("status")
        
        if not tool_name or not status:
            continue
        
        if tool_name not in tool_tracking:
            tool_tracking[tool_name] = {"started": 0, "final": 0}
        
        if status == "started":
            tool_tracking[tool_name]["started"] += 1
        elif status in ("succeeded", "failed"):
            tool_tracking[tool_name]["final"] += 1
    
    # Warn about unpaired events
    for tool_name, counts in tool_tracking.items():
        if counts["started"] != counts["final"]:
            errors.append(
                f"Tool '{tool_name}': Mismatched event pairs "
                f"({counts['started']} started, {counts['final']} final). "
                f"Each 'started' should have a 'succeeded' or 'failed'."
            )
    
    return len(errors) == 0, errors


def validate_file(filepath: str) -> None:
    """Validate response from JSON file."""
    try:
        with open(filepath, 'r') as f:
            response = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON: {e}")
        sys.exit(1)
    
    is_valid, errors = validate_response(response)
    
    if is_valid:
        print("✅ Response is valid!")
        
        # Print summary
        body = response.get("body", {})
        tool_calls = body.get("tool_calls", [])
        
        if not tool_calls:
            print("   No tool calls (valid)")
        else:
            print(f"   Found {len(tool_calls)} tool call events")
            
            # Count unique tools
            tools_used = set()
            for event in tool_calls:
                if isinstance(event, dict):
                    tool_name = event.get("tool_name")
                    if tool_name:
                        tools_used.add(tool_name)
            
            print(f"   Unique tools: {', '.join(sorted(tools_used))}")
    else:
        print("❌ Response is invalid!")
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


def print_example() -> None:
    """Print example valid response."""
    example = {
        "body": {
            "tool_calls": [
                {
                    "event_type": "tool_call",
                    "tool_name": "web_search",
                    "status": "started",
                    "input": {"query": "Python tutorials"}
                },
                {
                    "event_type": "tool_call",
                    "tool_name": "web_search",
                    "status": "succeeded",
                    "output": {"type": "str", "preview": "Found 10 results..."}
                }
            ],
            "answer": "Here are some Python tutorials...",
            "search_used": True
        }
    }
    
    print("Example valid response:")
    print(json.dumps(example, indent=2))


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python validate_response.py <response.json>")
        print("       python validate_response.py --example")
        sys.exit(1)
    
    if sys.argv[1] == "--example":
        print_example()
        sys.exit(0)
    
    validate_file(sys.argv[1])


if __name__ == "__main__":
    main()
