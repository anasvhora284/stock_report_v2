# Dynamic Attribute View Workflow

## Overview

The Dynamic Attribute View is a powerful Odoo module that provides an interactive matrix-style display of product variants based on their attributes. It allows inventory managers to quickly visualize stock quantities across product variants and filter them based on various criteria.

## Configuration Workflow

1. **Create a Configuration**:
   - Navigate to Inventory > Configuration > Dynamic Attribute Reports
   - Click "Create" to add a new configuration
   - Set a name for the configuration
   - Select attributes to display in the matrix view
   - Configure display options (hide zero quantities, include negative, use forecast)
   - Save the configuration

2. **Access the Report**:
   - A new menu item will be automatically created under the Inventory menu
   - Click on the menu item to open the report view

## User Workflow

1. **Viewing Product Matrix**:
   - The report displays products in a matrix format
   - Products with multiple attributes show in a matrix with primary/secondary attributes
   - Products with a single attribute show in a list format
   - Quantities are color-coded based on stock levels

2. **Filtering Products**:
   - Use the search bar to filter products by name
   - Use the dropdown to filter by quantity status:
     - All Products
     - Available (> 0)
     - Negative Stock (< 0)
     - Zero Stock (= 0)
     - Has Reserved
     - Has Incoming
     - Has Outgoing

3. **Variant Details**:
   - Click on any quantity cell to view detailed information about the variant
   - The variant details modal shows:
     - Product image
     - Complete attributes
     - On-hand quantity
     - Reserved quantity
     - Incoming quantity
     - Outgoing quantity
   - Click "Open Product" to navigate to the product form

4. **Refreshing Data**:
   - Click the "Refresh" button to reload the latest stock data

5. **Navigating Large Datasets**:
   - For large product catalogs, the report uses pagination
   - Navigate through pages using the controls at the bottom
   - View the total product count and current page information
   - The system loads only the necessary data for each page, improving performance

## Technical Workflow

1. **Configuration Creation**:
   - `stock.report.config` model stores configuration
   - On creation/update, a client action and menu item are automatically created

2. **Data Loading**:
   - Client action context passes configuration ID to the frontend component
   - Frontend component loads configuration details
   - Frontend calls `get_report_data_by_config` to fetch data with pagination
   - Data is processed and displayed in the matrix format

3. **Pagination Handling**:
   - Page size limits the number of products loaded at once (default 20)
   - Backend uses SQL optimization with LIMIT and OFFSET for efficient queries
   - The system tracks total product count for proper pagination
   - Frontend maintains current page state and updates data on page change

4. **Matrix Generation**:
   - For products with multiple attributes, a matrix is generated
   - First attribute becomes row headers
   - Second attribute becomes column headers
   - Cells contain variants with matching attribute combinations
   - Cells are color-coded based on quantity levels

5. **User Interactions**:
   - Filtering by criteria operates on the loaded dataset
   - Searching by name sends a new request with search parameters
   - Clicking on cells opens a modal with pre-loaded variant details
   - Refreshing fetches new data from the server
   - Pagination controls load different subsets of the dataset 