"""The real backends: each module fills one interface from one web service.

They share `http.py`, which sends with the plugin's own User-Agent, keeps each service's rate,
and turns every failure into the plugin's own error at the edge. That error never carries the
request: a URL holds what was searched for, and later a position.
"""
