import pandas as pd
import csv

def csv_to_string(filepath):
    """Convert CSV content to a formatted string"""
    try:
        result = []
        with open(filepath, 'r', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            next(csv_reader)  # Skip header
            for row in csv_reader:
                if len(row) >= 2:
                    result.append(f"Question: {row[0]}, Answer: {row[1]}")
        return "\n".join(result)
    except Exception as e:
        print(f"Error reading CSV {filepath}: {str(e)}")
        return ""

def close_ended_response(username):
    """Get close-ended responses for specific user"""
    try:
        filepath = f"responses/close_ended/{username}.csv"
        return csv_to_string(filepath)
    except Exception as e:
        print(f"Error getting close-ended responses: {str(e)}")
        return ""

def open_ended_response(username):
    """Get open-ended responses for specific user"""
    try:
        filepath = f"responses/open_ended/{username}.csv"
        return csv_to_string(filepath)
    except Exception as e:
        print(f"Error getting open-ended responses: {str(e)}")
        return ""
