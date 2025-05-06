# -*- coding: utf-8 -*-
from odoo import api, models, fields, tools, _
import logging
from odoo.exceptions import UserError
from collections import defaultdict

_logger = logging.getLogger(__name__)

class ProductAttributeReport(models.Model):
    _name = 'product.attribute.report'
    _description = 'Product Attribute Report'
    _auto = False
    _rec_name = 'product_name'
    _order = 'product_name, attribute_name'
    
    id = fields.Integer(readonly=True)
    product_id = fields.Many2one('product.product', string='Product Variant', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', readonly=True)
    product_name = fields.Char(string='Product Name', readonly=True)
    default_code = fields.Char(string='Internal Reference', readonly=True)
    attribute_id = fields.Many2one('product.attribute', string='Attribute', readonly=True)
    attribute_name = fields.Char(string='Attribute Name', readonly=True)
    attribute_value_id = fields.Many2one('product.attribute.value', string='Attribute Value', readonly=True)
    attribute_value = fields.Char(string='Attribute Value', readonly=True)
    qty_available = fields.Float(string='Quantity On Hand', readonly=True, digits='Product Unit of Measure')
    virtual_available = fields.Float(string='Forecast Quantity', readonly=True, digits='Product Unit of Measure')
    incoming_qty = fields.Float(string='Incoming', readonly=True, digits='Product Unit of Measure')
    outgoing_qty = fields.Float(string='Outgoing', readonly=True, digits='Product Unit of Measure')
    reserved_qty = fields.Float(string='Reserved', readonly=True, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True)
    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("DROP TABLE IF EXISTS %s CASCADE" % self._table)
        
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH stock_data AS (
                    SELECT 
                        sq.product_id,
                        SUM(sq.quantity) as qty_available,
                        SUM(sq.reserved_quantity) as reserved_qty
                    FROM stock_quant sq
                    JOIN stock_location sl ON sq.location_id = sl.id
                    WHERE sl.usage = 'internal'
                    GROUP BY sq.product_id
                )
                
                SELECT
                    ROW_NUMBER() OVER() AS id,
                    pp.id AS product_id,
                    pt.id AS product_tmpl_id,
                    pt.name AS product_name,
                    pp.default_code AS default_code,
                    pa.id AS attribute_id,
                    pa.name AS attribute_name,
                    pav.id AS attribute_value_id,
                    pav.name AS attribute_value,
                    COALESCE(sd.qty_available, 0) AS qty_available,
                    0.0 AS virtual_available,
                    0.0 AS incoming_qty, 
                    0.0 AS outgoing_qty,
                    COALESCE(sd.reserved_qty, 0) AS reserved_qty,
                    pt.uom_id AS uom_id
                FROM product_product pp
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                LEFT JOIN product_template_attribute_value ptav ON ptav.product_tmpl_id = pt.id
                LEFT JOIN product_attribute_value pav ON ptav.product_attribute_value_id = pav.id
                LEFT JOIN product_attribute pa ON pav.attribute_id = pa.id
                LEFT JOIN stock_data sd ON pp.id = sd.product_id
                WHERE pt.active = true AND pt.type = 'product'
            )
        """ % self._table)

    @api.model
    def get_attribute_data(self, options=None):
        if not options:
            options = {}
        
        attribute_ids = options.get('attribute_ids', [])
        filter_zero = options.get('filter_zero', False)
        include_negative = options.get('include_negative', True)
        use_forecast = options.get('use_forecast', False)
        limit = options.get('limit', 500)
        offset = options.get('offset', 0)
        search_term = options.get('search_term', '')
        
        attributes = self.env['product.attribute'].browse(attribute_ids or [])
        if not attributes and not attribute_ids:
            attributes = self.env['product.attribute'].search([], limit=10)

        params = []
        
        query = """
            WITH stock_data AS (
                SELECT 
                    sq.product_id,
                    SUM(sq.quantity) as qty_available,
                    SUM(sq.reserved_quantity) as reserved_qty
                FROM stock_quant sq
                JOIN stock_location sl ON sq.location_id = sl.id
                WHERE sl.usage = 'internal'
                GROUP BY sq.product_id
            )
            SELECT
                pp.id, pp.product_tmpl_id, pt.name, pp.default_code,
                COALESCE(sd.qty_available, 0) as qty_available,
                COALESCE(sm_in.incoming_qty, 0) as incoming_qty,
                COALESCE(sm_out.outgoing_qty, 0) as outgoing_qty,
                pt.uom_id, uu.name as uom_name,
                COALESCE(sd.reserved_qty, 0) as reserved_qty
            FROM product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            LEFT JOIN stock_data sd ON pp.id = sd.product_id
            LEFT JOIN (
                SELECT product_id, SUM(product_qty) as incoming_qty 
                FROM stock_move 
                WHERE state IN ('assigned', 'confirmed', 'waiting') 
                  AND location_dest_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
                  AND location_id NOT IN (SELECT id FROM stock_location WHERE usage = 'internal')
                GROUP BY product_id
            ) sm_in ON pp.id = sm_in.product_id
            LEFT JOIN (
                SELECT product_id, SUM(product_qty) as outgoing_qty 
                FROM stock_move 
                WHERE state IN ('assigned', 'confirmed', 'waiting') 
                  AND location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
                  AND location_dest_id NOT IN (SELECT id FROM stock_location WHERE usage = 'internal')
                GROUP BY product_id
            ) sm_out ON pp.id = sm_out.product_id
            LEFT JOIN uom_uom uu ON pt.uom_id = uu.id
            WHERE pt.active = true AND pt.type = 'product'
        """
        
        # Add attribute filter
        if attribute_ids:
            query += """
                AND pt.id IN (
                    SELECT product_tmpl_id 
                    FROM product_template_attribute_value 
                    WHERE attribute_id IN %s
                )
            """
            params.append(tuple(attribute_ids) if len(attribute_ids) > 1 else (attribute_ids[0],))
        
        # Add search filter
        if search_term:
            query += """
                AND (
                    pt.name ILIKE %s
                    OR pp.default_code ILIKE %s
                )
            """
            search_pattern = f'%{search_term}%'
            params.extend([search_pattern, search_pattern])
        
        # Add quantity filters
        if filter_zero:
            query += " AND COALESCE(sd.qty_available, 0) != 0"
        
        if not include_negative:
            query += " AND COALESCE(sd.qty_available, 0) >= 0"
        
        # Add pagination
        query += " ORDER BY pt.name LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        self.env.cr.execute(query, params)
        products = self.env.cr.dictfetchall()
        
        if not products:
            return {'products': [], 'variants': [], 'attributes': self._prepare_attribute_data(attributes)}
        
        # Get attribute values efficiently with a single query
        product_ids = [p['id'] for p in products]
        
        # Default empty attributes if no products
        product_attributes = {}
        
        if product_ids:
            attribute_query = """
                SELECT 
                    pp.id AS product_id,
                    pa.id AS attribute_id,
                    pav.id AS value_id
                FROM product_product pp
                JOIN product_template_attribute_value ptav ON ptav.ptav_product_variant_ids @> ARRAY[pp.id]
                JOIN product_attribute_value pav ON ptav.product_attribute_value_id = pav.id
                JOIN product_attribute pa ON pav.attribute_id = pa.id
                WHERE pp.id IN %s
            """
            self.env.cr.execute(attribute_query, [tuple(product_ids) if len(product_ids) > 1 else (product_ids[0],)])
            attribute_data = self.env.cr.dictfetchall()
            
            # Organize attribute data by product
            for attr in attribute_data:
                if attr['product_id'] not in product_attributes:
                    product_attributes[attr['product_id']] = {}
                product_attributes[attr['product_id']][attr['attribute_id']] = attr['value_id']
        
        # Prepare product and variant data
        for product in products:
            product['image_url'] = f'/web/image/product.product/{product["id"]}/image_1920'
            product['reserved_quantity'] = product['reserved_qty']
            product['virtual_available'] = product['qty_available'] - product['reserved_qty'] + product['incoming_qty']
        
        variants = []
        for product in products:
            main_qty = product['virtual_available'] if use_forecast else product['qty_available']
            
            variants.append({
                'id': product['id'],
                'product_id': product['id'],
                'product_tmpl_id': product['product_tmpl_id'],
                'name': product['name'],
                'default_code': product['default_code'],
                'qty': main_qty,
                'qty_on_hand': product['qty_available'],
                'qty_available': product['virtual_available'],
                'qty_incoming': product['incoming_qty'],
                'qty_outgoing': product['outgoing_qty'],
                'qty_reserved': product['reserved_qty'],
                'uom_id': product['uom_id'],
                'uom_name': product['uom_name'],
                'product_url': f'/web#id={product["id"]}&model=product.product&view_type=form',
                'image_url': f'/web/image/product.product/{product["id"]}/image_1920',
                'attributes': product_attributes.get(product['id'], {})
            })
        
        # Get total count for pagination
        count_query = """
            SELECT COUNT(pp.id) as count
            FROM product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            LEFT JOIN (
                SELECT 
                    sq.product_id,
                    SUM(sq.quantity) as qty_available
                FROM stock_quant sq
                JOIN stock_location sl ON sq.location_id = sl.id
                WHERE sl.usage = 'internal'
                GROUP BY sq.product_id
            ) sd ON pp.id = sd.product_id
            WHERE pt.active = true AND pt.type = 'product'
        """
        
        count_params = []
        if attribute_ids:
            count_query += """
                AND pt.id IN (
                    SELECT product_tmpl_id 
                    FROM product_template_attribute_value 
                    WHERE attribute_id IN %s
                )
            """
            count_params.append(tuple(attribute_ids) if len(attribute_ids) > 1 else (attribute_ids[0],))
        
        if search_term:
            count_query += """
                AND (
                    pt.name ILIKE %s
                    OR pp.default_code ILIKE %s
                )
            """
            count_params.extend([f'%{search_term}%', f'%{search_term}%'])
        
        if filter_zero:
            count_query += " AND COALESCE(sd.qty_available, 0) != 0"
        
        if not include_negative:
            count_query += " AND COALESCE(sd.qty_available, 0) >= 0"
        
        self.env.cr.execute(count_query, count_params)
        count_result = self.env.cr.dictfetchone()
        total_count = count_result['count'] if count_result else 0
        
        return {
            'products': products,
            'variants': variants,
            'attributes': self._prepare_attribute_data(attributes),
            'total_count': total_count,
            'limit': limit,
            'offset': offset
        }
        
    def _get_total_product_count(self, options):
        """Get total count of products for pagination"""
        attribute_ids = options.get('attribute_ids', [])
        filter_zero = options.get('filter_zero', False)
        include_negative = options.get('include_negative', True)
        use_forecast = options.get('use_forecast', False)
        search_term = options.get('search_term', '')
        
        params = []
        query = """
            SELECT COUNT(pp.id) as count
            FROM product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            LEFT JOIN (
                SELECT product_id, SUM(quantity) as qty_available 
                FROM stock_quant 
                JOIN stock_location ON stock_quant.location_id = stock_location.id
                WHERE stock_location.usage = 'internal'
                GROUP BY product_id
            ) sq ON pp.id = sq.product_id
            WHERE pt.active = true AND pt.type = 'product'
        """
        
        if attribute_ids:
            query += """
                AND pt.id IN (
                    SELECT product_tmpl_id 
                    FROM product_template_attribute_value 
                    WHERE attribute_id IN %s
                )
            """
            params.append(tuple(attribute_ids))
        
        if search_term:
            query += """
                AND (
                    pt.name ILIKE %s
                    OR pp.default_code ILIKE %s
                )
            """
            search_pattern = f'%{search_term}%'
            params.extend([search_pattern, search_pattern])
        
        qty_field = 'virtual_available' if use_forecast else 'qty_available'
        if filter_zero:
            query += f" AND COALESCE(sq.qty_available, 0) != 0"
        
        if not include_negative:
            query += f" AND COALESCE(sq.qty_available, 0) >= 0"
        
        self.env.cr.execute(query, params)
        result = self.env.cr.dictfetchone()
        return result['count'] if result else 0
    
    @api.model
    def get_report_data_by_config(self, config_id):
        """Get report data based on configuration ID with pagination support"""
        params = self.env.context.get('params', {})
        page = int(params.get('page', 1))
        page_size = int(params.get('page_size', 20))
        search_term = params.get('search_term', '')
        
        if not config_id:
            return {'error': 'No configuration ID provided'}
            
        config = self.env['stock.report.config'].browse(config_id)
        if not config.exists():
            return {'error': 'Configuration not found'}
            
        # Calculate offset for pagination
        offset = (page - 1) * page_size
        
        options = {
            'attribute_ids': config.attribute_ids.ids,
            'filter_zero': config.filter_zero,
            'include_negative': config.include_negative,
            'use_forecast': config.use_forecast,
            'limit': page_size,
            'offset': offset,
            'search_term': search_term
        }
        
        # Get data with pagination
        data = self.get_attribute_data(options)
        
        # Group variants by product template
        templates = {}
        template_variants = defaultdict(list)
        
        for variant in data['variants']:
            template_id = variant['product_tmpl_id']
            if template_id not in templates:
                # Get template data without loading the whole record
                query = """
                    SELECT id, name 
                    FROM product_template 
                    WHERE id = %s
                """
                self.env.cr.execute(query, [template_id])
                template_data = self.env.cr.dictfetchone()
                
                templates[template_id] = {
                    'id': template_id,
                    'name': template_data['name'],
                    'image': f'/web/image/product.template/{template_id}/image_1920',
                    'product_url': f'/web#id={template_id}&model=product.template&view_type=form',
                    'attributes': {},
                    'variants': []
                }
                
            template_variants[template_id].append(variant)
        
        result = {
            'attributes': data['attributes'],
            'products': [],
            'pagination': {
                'total': data.get('total_count', 0),
                'page': page,
                'page_size': page_size,
                'pages': (data.get('total_count', 0) + page_size - 1) // page_size if data.get('total_count', 0) > 0 else 1
            }
        }
        
        # Get template attributes with a single optimized query if we have templates
        if templates:
            template_ids = list(templates.keys())
            if template_ids:
                attr_query = """
                    SELECT 
                        tal.product_tmpl_id,
                        pa.id AS attribute_id,
                        pa.name AS attribute_name,
                        pav.id AS value_id,
                        pav.name AS value_name,
                        pav.html_color
                    FROM product_template_attribute_line tal
                    JOIN product_attribute pa ON tal.attribute_id = pa.id
                    JOIN product_attribute_value pav ON pav.id IN (
                        SELECT value_id FROM product_template_attribute_line_product_attribute_value_rel
                        WHERE line_id = tal.id
                    )
                    WHERE tal.product_tmpl_id IN %s
                """
                params = [tuple(template_ids)]
                
                if config.attribute_ids:
                    attr_query += " AND pa.id IN %s"
                    params.append(tuple(config.attribute_ids.ids))
                
                self.env.cr.execute(attr_query, params)
                attr_results = self.env.cr.dictfetchall()
                
                # Organize template attributes
                template_attr_data = {}
                for attr in attr_results:
                    tmpl_id = attr['product_tmpl_id']
                    attr_id = attr['attribute_id']
                    
                    if tmpl_id not in template_attr_data:
                        template_attr_data[tmpl_id] = {}
                        
                    if attr_id not in template_attr_data[tmpl_id]:
                        template_attr_data[tmpl_id][attr_id] = {
                            'id': attr_id,
                            'name': attr['attribute_name'],
                            'values': []
                        }
                    
                    # Add value if not already added
                    value_exists = any(v['id'] == attr['value_id'] for v in template_attr_data[tmpl_id][attr_id]['values'])
                    if not value_exists:
                        template_attr_data[tmpl_id][attr_id]['values'].append({
                            'id': attr['value_id'],
                            'name': attr['value_name'],
                            'html_color': attr['html_color']
                        })
                
                # Now populate product data
                for template_id, template_data in templates.items():
                    variants = template_variants[template_id]
                    
                    product_data = {
                        'id': template_id,
                        'name': template_data['name'],
                        'image_url': template_data['image'],
                        'product_url': template_data['product_url'],
                        'variants': variants,
                        'template_attributes': template_attr_data.get(template_id, {})
                    }
                    
                    result['products'].append(product_data)
        
        return result
        
    def _prepare_attribute_data(self, attributes):
        result = []
        for attribute in attributes:
            values = []
            for value in attribute.value_ids:
                values.append({
                    'id': value.id,
                    'name': value.name,
                    'display_name': value.display_name or value.name,
                    'html_color': value.html_color or None,
                })
            result.append({
                'id': attribute.id,
                'name': attribute.name,
                'display_type': attribute.display_type,
                'values': values,
            })
        return result
        
    @api.model
    def get_attribute_matrix(self, template_id, attribute_ids=None):
        product_tmpl = self.env['product.template'].browse(template_id)
        if not product_tmpl:
            return {'error': 'Product template not found'}
            
        attribute_lines = product_tmpl.attribute_line_ids
        if not attribute_lines:
            return {'error': 'Product has no attributes'}
            
        attributes = attribute_lines.mapped('attribute_id')
        
        if attribute_ids:
            attributes = attributes.filtered(lambda a: a.id in attribute_ids)
            
        if len(attributes) < 1:
            return {'error': 'No valid attributes found for this product'}
            
        matrix = {
            'template': {
                'id': product_tmpl.id,
                'name': product_tmpl.name,
                'default_code': product_tmpl.default_code,
                'image_url': f'/web/image/product.template/{product_tmpl.id}/image_1024',
            },
            'attributes': [],
            'variants': [],
        }
        
        for attribute in attributes:
            attr_line = attribute_lines.filtered(lambda l: l.attribute_id.id == attribute.id)
            values = []
            for value in attr_line.value_ids:
                values.append({
                    'id': value.id,
                    'name': value.name,
                    'html_color': value.html_color or None,
                })
            matrix['attributes'].append({
                'id': attribute.id,
                'name': attribute.name,
                'display_type': attribute.display_type,
                'values': values,
            })
        
        for variant in product_tmpl.product_variant_ids:
            variant_data = {
                'id': variant.id,
                'name': variant.name,
                'default_code': variant.default_code,
                'qty_available': variant.qty_available,
                'virtual_available': variant.virtual_available,
                'incoming_qty': variant.incoming_qty,
                'outgoing_qty': variant.outgoing_qty,
                'reserved_qty': variant.qty_available - (variant.virtual_available - variant.incoming_qty),
                'image_url': f'/web/image/product.product/{variant.id}/image_1024',
                'attribute_values': {},
            }
            
            for ptav in variant.product_template_attribute_value_ids:
                if ptav.attribute_id.id in attributes.ids:
                    variant_data['attribute_values'][ptav.attribute_id.id] = {
                        'id': ptav.product_attribute_value_id.id,
                        'name': ptav.product_attribute_value_id.name,
                    }
            
            matrix['variants'].append(variant_data)
        
        return matrix 