"""Interface layer: translates HTTP <-> the service layer.

Routes stay thin: parse the request, check auth, call ONE service method, turn its
Outcome into a response (app/api/responses.py). No business rules here, no SQL here.
"""
