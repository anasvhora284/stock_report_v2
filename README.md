# Dynamic Attribute Stock Report

A powerful Odoo module that provides a dynamic, matrix-style view for visualizing product variants and their stock quantities based on product attributes.

## Features

- **Matrix Display**: View product variants in an interactive matrix organized by attributes
- **Real-time Filtering**: Filter products by stock status or search by name
- **Visual Indicators**: Color-coded quantity cells for quick stock level assessment
- **Variant Details**: Detailed modal view showing comprehensive variant information
- **Configurable Reports**: Create multiple report configurations with different attributes
- **Auto-generated Menus**: Each configuration automatically creates its own menu entry
- **Optimized Performance**: Efficient SQL queries and pagination for handling large datasets (5000+ products)

## Installation

1. Clone the repository to your Odoo addons directory:
   ```
   git clone https://github.com/anasvhora284/stock_report_v2.git
   ```

2. Update your Odoo modules list and install the module:
   - Go to Apps menu
   - Click "Update Apps List"
   - Search for "Dynamic Attribute Stock Report"
   - Click Install

## Configuration

1. After installation, go to **Inventory > Configuration > Dynamic Attribute Reports**
2. Create a new configuration:
   - Set a name for the report
   - Select attributes to display in the matrix (1 or 2 attributes recommended)
   - Choose display options (show/hide zero quantities, etc.)
   - Save to automatically create a menu entry

## Usage

1. Navigate to the report using the generated menu entry in the Inventory menu
2. The report displays your products in a matrix or list format based on the configured attributes
3. Use the search bar to filter products by name
4. Use the dropdown to filter by quantity status (available, negative, zero, etc.)
5. Click on any quantity cell to view detailed information about that variant
6. Use the "Refresh" button to update data with the latest stock information
7. Navigate between pages using the pagination controls at the bottom for large datasets

## Performance

The module is optimized for handling large product catalogs:

- Pagination support breaks large datasets into manageable chunks
- Direct SQL queries for better performance than ORM for large datasets
- Image loading optimizations to improve page rendering speed
- Client-side filtering for faster user experience after initial load
- Efficient matrix generation algorithm for variant display

## Technical Documentation

For detailed technical information and development notes, please see:

- [Workflow Documentation](./doc/workflow.md) - Detailed user and technical workflows
- [Developer Insights](./doc/developer_insight.md) - Architecture, data flow, and development guide

## Requirements

- Odoo 17.0
- Inventory (Stock) module

## Support

For issues, feature requests, or contributions, please create an issue in the repository or contact support at support@yourcompany.com.
