from app.models.declared_routes import DeclaredRouteModel
from typing import List
import json
from app.database import get_declared_routes_collection, get_fleets_collection
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, WebSocket
from fastapi import Path
from app.dependencies.roles import super_and_admin_required, admin_required
from bson import ObjectId
from app.utils.ws_manager import routes_all_manager, notification_manager
from app.database import notifications_collection
from datetime import datetime

router = APIRouter(prefix="/declared_routes", tags=["Declared Routes"])

@router.websocket("/ws/routes")
async def websocket_endpoint(websocket: WebSocket):
    try:
        # Let the connection manager handle the acceptance
        await routes_all_manager.connect(websocket)
        print(f"🔌 DEBUG: WebSocket connection accepted from {websocket.client}")
        
        # Wait for client to identify itself with role
        data = await websocket.receive_text()
        message = json.loads(data)
        user_role = message.get("role", "all")
        user_id = message.get("user_id", "")
        
        print(f"🔌 DEBUG: WebSocket authenticated - Role: {user_role}, User ID: {user_id}")
        
        # Also connect to notification manager with role
        await notification_manager.connect(websocket, user_role)
        
        print(f"✅ DEBUG: Added to managers - routes_all_manager: {len(routes_all_manager.active_connections)}, notification_manager[{user_role}]: {len(notification_manager.active_connections.get(user_role, []))}")
        
        # Keep the connection alive and handle messages
        while True:
            try:
                data = await websocket.receive_text()
                # Optional: handle any incoming messages from client
                # print(f"📨 DEBUG: Received message from client: {data}")
            except Exception as e:
                print(f"❌ DEBUG: Error receiving message: {str(e)}")
                break
                
    except Exception as e:
        print(f"❌ DEBUG: WebSocket error: {str(e)}")
        import traceback
        print(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
    finally:
        # Clean up on disconnect
        routes_all_manager.disconnect(websocket)
        notification_manager.disconnect(websocket)
        print(f"🔌 DEBUG: WebSocket disconnected and cleaned up")

@router.delete("/{route_id}")
async def delete_declared_route(
    route_id: str,
    current_user: dict = Depends(admin_required)
):
    try:
        # Get the collection
        routes_collection = get_declared_routes_collection
        
        # Fetch the route before deletion to get details for broadcast
        route_to_delete = routes_collection.find_one({"_id": ObjectId(route_id)})
        if not route_to_delete:
            raise HTTPException(status_code=404, detail="Route not found")
        
        # Delete the route
        result = routes_collection.delete_one({"_id": ObjectId(route_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Route not found")
        
        # Broadcast deletion to all connected superadmin clients
        await routes_all_manager.broadcast({
            "type": "deleted_route",
            "route_id": str(route_to_delete["_id"]),
            "company_id": str(route_to_delete["company_id"])
        })
        
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{route_id}")
async def update_declared_route(
    route_id: str,
    start_location: str = Form(None),
    end_location: str = Form(None),
    landmark_details_start: str = Form(None),
    landmark_details_end: str = Form(None),
    current_user: dict = Depends(super_and_admin_required)
):
    try:
        update_data = {}
        if start_location is not None:
            update_data["start_location"] = start_location
        if end_location is not None:
            update_data["end_location"] = end_location
        if landmark_details_start is not None:
            update_data["landmark_details_start"] = landmark_details_start
        if landmark_details_end is not None:
            update_data["landmark_details_end"] = landmark_details_end

        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")

        # Update and get the full updated document
        result = get_declared_routes_collection.find_one_and_update(
            {"_id": ObjectId(route_id)},
            {"$set": update_data},
            return_document=True  # Returns the updated document
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Route not found")
        
        # Get company name for broadcast
        fleet = get_fleets_collection.find_one({"_id": ObjectId(str(result["company_id"]))})
        company_name = fleet.get("company_name", "Unknown Company") if fleet else "Unknown Company"
        
        # Prepare updated route data for broadcast
        broadcast_route = {
            "_id": str(result["_id"]),
            "company_name": company_name,
            "start_location": result.get("start_location", ""),
            "end_location": result.get("end_location", ""),
            "landmark_details_start": result.get("landmark_details_start", ""),
            "landmark_details_end": result.get("landmark_details_end", ""),
        }
        
        # Broadcast update to all connected superadmin clients
        await routes_all_manager.broadcast({
            "type": "updated_route",
            "route": broadcast_route
        })
            
        return {"updated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{company_id}")
async def get_declared_routes_by_company(company_id: str, current_user: dict = Depends(admin_required)):
    try:
        routes = list(get_declared_routes_collection.find({"company_id": company_id}))
        
        # Fetch company name once
        fleet = get_fleets_collection.find_one({"_id": ObjectId(company_id)})
        company_name = fleet.get("company_name", "Unknown Company") if fleet else "Unknown Company"
        
        result = []
        for route in routes:
            route["_id"] = str(route["_id"])  # Convert ObjectId to string
            route["company_name"] = company_name
            result.append(route)
        
        return result  # Return raw dict without Pydantic validation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[DeclaredRouteModel])
async def list_declared_routes(
    company_id: str,
    current_user: dict = Depends(super_and_admin_required)
):
    try:
        routes = list(get_declared_routes_collection.find(
            {"company_id": company_id}))
        for route in routes:
            route["_id"] = str(route["_id"])
        return [DeclaredRouteModel(**route) for route in routes]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{route_id}/route-geojson-upload", response_model=dict)
async def update_route_geojson(
    route_id: str = Path(..., description="Declared route ID"),
    route_geojson: UploadFile = File(...),
    current_user: dict = Depends(super_and_admin_required)
):
    """
    Upload GeoJSON to a route and notify the company
    """
    try:
        # Read and validate GeoJSON
        geojson_content = await route_geojson.read()
        route_geojson_dict = json.loads(geojson_content)
        
        # Fetch the route to get company info
        route = get_declared_routes_collection.find_one({"_id": ObjectId(route_id)})
        if not route:
            raise HTTPException(status_code=404, detail="Declared route not found")
        
        company_id = str(route["company_id"])
        
        # Get company details
        fleet = get_fleets_collection.find_one({"_id": ObjectId(company_id)})
        company_name = fleet.get("company_name", "Unknown Company") if fleet else "Unknown Company"
        
        # Update route with GeoJSON
        result = get_declared_routes_collection.update_one(
            {"_id": ObjectId(route_id)},
            {"$set": {"route_geojson": route_geojson_dict}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Declared route not found")
        
        # Get admin user info (the one uploading)
        superadmin_name = current_user.get("username", "SuperAdmin")
        
        # Create notification data
        notification_data = {
            "type": "geojson_uploaded_notification",
            "notification": {
                "id": route_id,
                "title": "GeoJSON File Uploaded",
                "description": f"{superadmin_name} has uploaded a GeoJSON file for your route '{route['start_location']} → {route['end_location']}'",
                "type": "geojson_uploaded",
                "is_read": False,
                "created_at": datetime.utcnow().isoformat(),
                "data": {
                    "route_id": route_id,
                    "route_name": f"{route['start_location']} → {route['end_location']}",
                    "company_id": company_id,
                    "company_name": company_name,
                    "uploaded_by": superadmin_name,
                    "uploaded_by_id": current_user.get("id", ""),
                    "file_name": route_geojson.filename,
                    "start_location": route["start_location"],
                    "end_location": route["end_location"]
                }
            }
        }
        
        # Save notification to database (for company admins who are offline)
        try:
            db_notification = {
                "title": "GeoJSON File Uploaded",
                "description": f"{superadmin_name} has uploaded a GeoJSON file for your route '{route['start_location']} → {route['end_location']}'",
                "type": "geojson_uploaded",
                "recipient_roles": ["admin"],  # Only admins of that company
                "recipient_ids": [company_id],  # Specific to this company
                "data": {
                    "route_id": route_id,
                    "route_name": f"{route['start_location']} → {route['end_location']}",
                    "company_id": company_id,
                    "company_name": company_name,
                    "uploaded_by": superadmin_name,
                    "file_name": route_geojson.filename,
                    "start_location": route["start_location"],
                    "end_location": route["end_location"]
                },
                "is_read": False,
                "created_at": datetime.utcnow(),
                "created_by": current_user.get("id", "system")
            }
            
            notifications_collection.insert_one(db_notification)
            print(f"💾 DEBUG: GeoJSON upload notification saved to database for company {company_id}")
            
        except Exception as db_error:
            print(f"⚠️ DEBUG: Failed to save GeoJSON notification to database: {str(db_error)}")
        
        # Send real-time notification via WebSocket to connected admins
        try:
            await routes_all_manager.broadcast(notification_data)
            print(f"📢 DEBUG: Real-time GeoJSON notification sent to {len(routes_all_manager.active_connections)} connected client(s)")
            
        except Exception as ws_error:
            print(f"⚠️ DEBUG: WebSocket broadcast failed: {str(ws_error)}")
        
        # Also send to notification manager for the specific company
        try:
            # Send to admins with role "admin"
            await notification_manager.broadcast_to_role(notification_data, "admin")
            print(f"👥 DEBUG: GeoJSON notification sent to admin connections")
        except Exception as nm_error:
            print(f"⚠️ DEBUG: Notification manager broadcast failed: {str(nm_error)}")
        
        return {"updated": True}
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid GeoJSON file format")
    except Exception as e:
        print(f"❌ DEBUG: Error uploading GeoJSON: {str(e)}")
        import traceback
        print(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/route-register", response_model=dict)
async def upload_declared_route(
    company_id: str = Form(...),
    start_location: str = Form(...),
    end_location: str = Form(...),
    landmark_details_start: str = Form(...),
    landmark_details_end: str = Form(...),
    route_geojson: UploadFile = File(None),
    current_user: dict = Depends(admin_required)
):
    """
    Create a new route and send real-time notification to superadmins
    """
    try:
        print(f"🚀 DEBUG: Route creation started by {current_user.get('username', 'Unknown')} (Role: {current_user.get('role', 'Unknown')})")
        
        # Validate required fields
        if not start_location.strip() or not end_location.strip():
            raise HTTPException(status_code=400, detail="Start and end locations are required")
        
        # Handle GeoJSON file if provided
        route_geojson_dict = None
        if route_geojson:
            try:
                geojson_content = await route_geojson.read()
                route_geojson_dict = json.loads(geojson_content)
                print("✅ DEBUG: GeoJSON file processed successfully")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid GeoJSON file format")
            except Exception as e:
                print(f"⚠️ DEBUG: Error processing GeoJSON: {str(e)}")
                # Continue without GeoJSON if there's an error
        
        # Prepare route data
        data = {
            "company_id": company_id,
            "start_location": start_location.strip(),
            "end_location": end_location.strip(),
            "landmark_details_start": landmark_details_start.strip() if landmark_details_start else "",
            "landmark_details_end": landmark_details_end.strip() if landmark_details_end else "",
            "route_geojson": route_geojson_dict,
            "created_by_id": current_user.get("id", ""),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Insert route into database
        result = get_declared_routes_collection.insert_one(data)
        inserted_id = str(result.inserted_id)
        
        print(f"✅ DEBUG: Route created with ID: {inserted_id}")
        print(f"📍 DEBUG: Route: {start_location} → {end_location}")
        
        # Get company name for notification
        fleet = get_fleets_collection.find_one({"_id": ObjectId(company_id)})
        company_name = fleet.get("company_name", "Unknown Company") if fleet else "Unknown Company"
        
        print(f"🏢 DEBUG: Company: {company_name}")
        
        # Prepare real-time notification data
        notification_data = {
            "type": "new_route_notification",
            "notification": {
                "id": inserted_id,
                "title": "New Route Created",
                "description": f"New route '{start_location} → {end_location}' from {company_name}",
                "type": "route_added",
                "is_read": False,
                "created_at": datetime.utcnow().isoformat(),
                "data": {
                    "route_id": inserted_id,
                    "route_name": f"{start_location} → {end_location}",
                    "company_name": company_name,
                    "created_by_id": current_user.get("id", ""),
                    "company_id": company_id,
                    "start_location": start_location,
                    "end_location": end_location,
                    "landmark_details_start": landmark_details_start,
                    "landmark_details_end": landmark_details_end
                }
            }
        }
        
        # Save notification to database for superadmins (for persistence)
        try:
            from app.database import notifications_collection
            
            db_notification = {
                "title": "New Route Created",
                "description": f"New route '{start_location} → {end_location}' from {company_name}",
                "type": "route_added",
                "recipient_roles": ["superadmin"],  # Only superadmins can see route creation notifications
                "recipient_ids": [],  # Empty = all superadmins
                "data": {
                    "route_id": inserted_id,
                    "route_name": f"{start_location} → {end_location}",
                    "company_name": company_name,
                    "created_by_id": current_user.get("id", ""),
                    "company_id": company_id,
                    "start_location": start_location,
                    "end_location": end_location,
                    "landmark_details_start": landmark_details_start,
                    "landmark_details_end": landmark_details_end
                },
                "is_read": False,
                "created_at": datetime.utcnow(),
                "created_by": current_user.get("id", "system")
            }
            
            notifications_collection.insert_one(db_notification)
            print("💾 DEBUG: Notification saved to database for superadmins")
            
        except Exception as db_error:
            print(f"⚠️ DEBUG: Failed to save notification to database: {str(db_error)}")
            # Continue with real-time notification even if DB save fails
        
        # Send real-time notification via WebSocket
        print(f"📢 DEBUG: Sending real-time notification...")
        print(f"📊 DEBUG: Active WebSocket connections: {len(routes_all_manager.active_connections)}")
        
        try:
            # Broadcast to all connected clients (real-time)
            await routes_all_manager.broadcast(notification_data)
            print(f"✅ DEBUG: Real-time notification sent successfully")
            print(f"🎯 DEBUG: Notification recipients: {len(routes_all_manager.active_connections)} connected client(s)")
            
        except Exception as ws_error:
            print(f"❌ DEBUG: WebSocket broadcast failed: {str(ws_error)}")
            # Don't fail the route creation if WebSocket fails
        
        # Also send to notification manager for role-based filtering (if needed)
        try:
            superadmin_connections = len(notification_manager.active_connections.get("superadmin", []))
            if superadmin_connections > 0:
                await notification_manager.broadcast_to_role(notification_data, "superadmin")
                print(f"👑 DEBUG: Also sent to {superadmin_connections} superadmin connection(s) via notification_manager")
        except Exception as nm_error:
            print(f"⚠️ DEBUG: Notification manager broadcast failed: {str(nm_error)}")
        
        # Return success response
        return {
            "success": True,
            "message": "Route created successfully",
            "inserted_id": inserted_id,
            "route_details": {
                "start_location": start_location,
                "end_location": end_location,
                "company_name": company_name
            },
            "notification_sent": True
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"❌ DEBUG: Critical error in route-register: {str(e)}")
        print(f"❌ DEBUG: Error type: {type(e).__name__}")
        import traceback
        print(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create route: {str(e)}")
    
# Add this new endpoint to your declared_routes.py file

@router.post("/route-register-public", response_model=dict)
async def upload_declared_route_public(
    company_code: str = Form(...),  # Use company_code instead of company_id
    start_location: str = Form(...),
    end_location: str = Form(...),
    landmark_details_start: str = Form(...),
    landmark_details_end: str = Form(...),
    route_geojson: UploadFile = File(None)
):
    """
    Create a new route during registration (no authentication required).
    Uses company_code to find the fleet since the user isn't logged in yet.
    """
    try:
        print(f"🚀 DEBUG: Public route creation started for company: {company_code}")
        
        # Validate required fields
        if not start_location.strip() or not end_location.strip():
            raise HTTPException(status_code=400, detail="Start and end locations are required")
        
        # Find the fleet by company_code
        fleet = get_fleets_collection.find_one({"company_code": company_code})
        if not fleet:
            raise HTTPException(status_code=404, detail="Company not found")
        
        company_id = str(fleet["_id"])
        company_name = fleet.get("company_name", "Unknown Company")
        
        # Only allow route creation for unverified or admin fleets
        if fleet.get("role") not in ["unverified", "admin"]:
            raise HTTPException(status_code=403, detail="Fleet status does not allow route creation")
        
        # Handle GeoJSON file if provided
        route_geojson_dict = None
        if route_geojson:
            try:
                geojson_content = await route_geojson.read()
                route_geojson_dict = json.loads(geojson_content)
                print("✅ DEBUG: GeoJSON file processed successfully")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid GeoJSON file format")
            except Exception as e:
                print(f"⚠️ DEBUG: Error processing GeoJSON: {str(e)}")
        
        # Prepare route data
        data = {
            "company_id": company_id,
            "start_location": start_location.strip(),
            "end_location": end_location.strip(),
            "landmark_details_start": landmark_details_start.strip() if landmark_details_start else "",
            "landmark_details_end": landmark_details_end.strip() if landmark_details_end else "",
            "route_geojson": route_geojson_dict,
            "created_by_id": company_id,  # Use company_id since no user is logged in
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Insert route into database
        result = get_declared_routes_collection.insert_one(data)
        inserted_id = str(result.inserted_id)
        
        print(f"✅ DEBUG: Route created with ID: {inserted_id}")
        print(f"📍 DEBUG: Route: {start_location} → {end_location}")
        print(f"🏢 DEBUG: Company: {company_name}")
        
        # Prepare notification data for superadmins
        notification_data = {
            "type": "new_route_notification",
            "notification": {
                "id": inserted_id,
                "title": "New Route from Registration",
                "description": f"New company '{company_name}' registered with route '{start_location} → {end_location}'",
                "type": "route_added",
                "is_read": False,
                "created_at": datetime.utcnow().isoformat(),
                "data": {
                    "route_id": inserted_id,
                    "route_name": f"{start_location} → {end_location}",
                    "company_name": company_name,
                    "company_id": company_id,
                    "company_code": company_code,
                    "start_location": start_location,
                    "end_location": end_location,
                    "landmark_details_start": landmark_details_start,
                    "landmark_details_end": landmark_details_end
                }
            }
        }
        
        # Save notification to database
        try:
            db_notification = {
                "title": "New Route from Registration",
                "description": f"New company '{company_name}' registered with route '{start_location} → {end_location}'",
                "type": "route_added",
                "recipient_roles": ["superadmin"],
                "recipient_ids": [],
                "data": notification_data["notification"]["data"],
                "is_read": False,
                "created_at": datetime.utcnow(),
                "created_by": "system"
            }
            
            notifications_collection.insert_one(db_notification)
            print("💾 DEBUG: Notification saved to database")
            
        except Exception as db_error:
            print(f"⚠️ DEBUG: Failed to save notification: {str(db_error)}")
        
        # Broadcast to WebSocket
        try:
            await routes_all_manager.broadcast(notification_data)
            print(f"✅ DEBUG: Real-time notification sent")
        except Exception as ws_error:
            print(f"⚠️ DEBUG: WebSocket broadcast failed: {str(ws_error)}")
        
        return {
            "success": True,
            "message": "Route created successfully",
            "inserted_id": inserted_id,
            "route_details": {
                "start_location": start_location,
                "end_location": end_location,
                "company_name": company_name
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ DEBUG: Error in route-register-public: {str(e)}")
        import traceback
        print(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create route: {str(e)}")

@router.get("/all/routes", response_model=List[DeclaredRouteModel])
async def get_all_declared_routes(current_user: dict = Depends(admin_required)):
    """
    Get all routes for the current user's company only
    """
    try:
        # Debug: Log current user
        print(f"🔍 DEBUG: current_user = {current_user}")
        
        # Get the current user's company ID (use fleet_id, not id)
        company_id = current_user.get("fleet_id")
        print(f"🔍 DEBUG: company_id = {company_id}")
        
        if not company_id:
            raise HTTPException(status_code=400, detail="User company ID not found")
        
        # Find all routes for this specific company
        routes = list(get_declared_routes_collection.find({"company_id": company_id}))
        print(f"✅ DEBUG: Found {len(routes)} routes for company {company_id}")
        
        # Get company name
        fleet = get_fleets_collection.find_one({"_id": ObjectId(company_id)})
        company_name = fleet.get("company_name", "Unknown Company") if fleet else "Unknown Company"
        print(f"🏢 DEBUG: company_name = {company_name}")
        
        # Add company name to each route
        for route in routes:
            route["_id"] = str(route["_id"])
            route["company_name"] = company_name
            
        result = [DeclaredRouteModel(**route) for route in routes]
        print(f"📤 DEBUG: Returning {len(result)} routes")
        return result
    
    except Exception as e:
        print(f"❌ ERROR in GET /all/routes: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/routes/{fleet_id}", response_model=List[dict])
async def get_routes_by_fleet_id(fleet_id: str, current_user: dict = Depends(admin_required)):
    """
    Get all start and end locations for a specific fleet/company (fleet_id).
    """
    try:
        routes_collection = get_declared_routes_collection
        fleets_collection = get_fleets_collection

        # Check if company exists
        company = fleets_collection.find_one({"_id": ObjectId(fleet_id)})
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get all routes belonging to this company
        routes = list(routes_collection.find({"company_id": fleet_id}, {
            "start_location": 1,
            "end_location": 1,
            "_id": 0
        }))

        if not routes:
            raise HTTPException(status_code=404, detail="No routes found for this company")

        return routes

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))