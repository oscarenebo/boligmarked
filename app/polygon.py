from shapely.geometry import Point, Polygon

# Create the polygon from user input
poly = Polygon([(12.56, 55.67), (12.58, 55.67), (12.58, 55.68)]) 

# Check if a property is inside
property_point = Point(12.57, 55.675)
is_inside = property_point.within(poly)