/** @odoo-module **/

import { Component, useState, onWillStart, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";

export class DynamicAttributeView extends Component {
    static template = "stock_report_v2.DynamicAttributeView";
    static components = { Layout };
    
    static props = {
        action: { type: Object },
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        
        this.layoutProps = {
            display: { controlPanel: false },
            className: "o_stock_report_layout",
        };
        
        const context = this.props.action.context || {};
        this.configId = context.config_id || false;
        
        this.state = useState({
            products: [],
            variants: [],
            attributes: [],
            filteredProducts: [],
            searchInput: "",
            filterType: "all",
            loading: true,
            expandedProducts: {},
            config: null,
            showVariantModal: false,
            selectedVariant: null
        });

        onWillStart(async () => {
            if (this.configId) {
                try {
                    const configs = await this.orm.call(
                        "stock.report.config",
                        "read",
                        [this.configId, ["name", "attribute_ids", "use_forecast", "filter_zero", "include_negative"]]
                    );
                    this.state.config = configs[0] || null;
                    await this.fetchData();
                } catch (error) {
                    console.error("Error loading data:", error);
                    this.notification.add(_t("Failed to load configuration"), { type: "danger" });
                }
            } else {
                this.notification.add(_t("No configuration provided"), { type: "warning" });
            }
        });

        onMounted(() => this.state.loading = false);
    }

    async fetchData() {
        try {
            if (!this.state.config) return;
            
            const result = await this.orm.call(
                "product.attribute.report",
                "get_report_data_by_config",
                [this.configId]
            );
            
            this.state.products = result.products || [];
            this.state.attributes = result.attributes || [];
            
            let allVariants = [];
            this.state.products.forEach(product => {
                if (product.variants && product.variants.length) {
                    allVariants = [...allVariants, ...product.variants];
                }
            });
            this.state.variants = allVariants;
            
            this.applyFilters();
        } catch (error) {
            console.error("Error fetching data:", error);
            this.notification.add(_t("Failed to fetch data"), { type: "danger" });
        }
    }

    applyFilters() {
        let filteredVariants = [...this.state.variants];
        
        if (this.state.searchInput) {
            const term = this.state.searchInput.toLowerCase();
            filteredVariants = filteredVariants.filter(v => 
                v.name.toLowerCase().includes(term)
            );
        }
        
        if (this.state.filterType === "negative") {
            filteredVariants = filteredVariants.filter(v => v.qty < 0);
        } else if (this.state.filterType === "zero") {
            filteredVariants = filteredVariants.filter(v => v.qty === 0);
        } else if (this.state.filterType === "positive") {
            filteredVariants = filteredVariants.filter(v => v.qty > 0);
        } else if (this.state.filterType === "reserved") {
            filteredVariants = filteredVariants.filter(v => v.qty_reserved > 0);
        } else if (this.state.filterType === "replenishment") {
            filteredVariants = filteredVariants.filter(v => v.qty_incoming > 0);
        } else if (this.state.filterType === "outgoing") {
            filteredVariants = filteredVariants.filter(v => v.qty_outgoing > 0);
        }
        
        const filteredProductIds = new Set(filteredVariants.map(v => v.product_tmpl_id));
        const filteredProducts = this.state.products.filter(p => filteredProductIds.has(p.id));
        
        const productsWithMatrix = filteredProducts.map(product => {
            const productVariants = filteredVariants.filter(v => v.product_tmpl_id === product.id);
            
            const productWithMatrix = { ...product, variants: productVariants };
            
            if (this.state.attributes.length > 1) {
                productWithMatrix.matrix_values = this._createAttributeMatrix(productWithMatrix);
            }
            
            return productWithMatrix;
        });
        
        this.state.filteredProducts = productsWithMatrix;
    }

    getQuantityClass(qty) {
        if (qty === 0) return "qty-available light-red";
        if (qty < 0) return "qty-available strong-red";
        if (qty <= 2) return "qty-available light-yellow";
        if (qty <= 4) return "qty-available light-green";
        if (qty <= 7) return "qty-available strong-green";
        return "qty-available strong-blue";
    }

    toggleProductDetails(productId) {
        this.state.expandedProducts[productId] = !this.state.expandedProducts[productId];
    }

    isProductExpanded(productId) {
        return this.state.expandedProducts[productId] || false;
    }

    getAttributeDisplayValue(attributeId, valueId) {
        const attrId = typeof attributeId === 'string' ? parseInt(attributeId, 10) : Number(attributeId);
        
        const attr = this.state.attributes.find(a => a.id === attrId);
        if (!attr) return valueId;
        
        const valueObj = attr.values.find(v => v.id === valueId);
        return valueObj ? valueObj.display_name || valueObj.name : valueId;
    }

    onSearchInput(value) {
        this.state.searchInput = value.trim().toLowerCase();
        this.applyFilters();
    }

    clearSearch() {
        this.state.searchInput = "";
        this.applyFilters();
        const searchInput = document.querySelector('.search-container input[type="text"]');
        if (searchInput) {
            searchInput.value = "";
        }
    }

    onFilterChange(value) {
        this.state.filterType = value;
        this.applyFilters();
    }

    refreshData() {
        this.state.loading = true;
        this.fetchData().then(() => {
            this.state.loading = false;
            this.notification.add(_t("Data refreshed"), { type: "success" });
        });
    }

    formatQty(qty) {
        return qty !== undefined && qty !== null ? Number(qty).toFixed(2) : '0.00';
    }
    
    showVariantDetails(variant) {
        if (!variant) return;
        
        const attributes = this.formatAttributesForDisplay(variant.attributes);
        const attributesList = attributes.map(attr => attr.value).join(', ');
        
        this.state.selectedVariant = {
            product: { name: variant.name.split(' (')[0] },
            id: variant.id,
            name: variant.name,
            default_code: variant.default_code,
            image: variant.image_url || '/stock_report_v2/static/src/img/no-image-found.png',
            qty: variant.qty || 0,
            qty_on_hand: variant.qty_on_hand || 0,
            qty_reserved: variant.qty_reserved || 0,
            qty_incoming: variant.qty_incoming || 0,
            qty_outgoing: variant.qty_outgoing || 0,
            attributes: attributes,
            attributesList: attributesList,
            quantityClass: this.getQuantityClass(variant.qty),
            product_url: variant.product_url
        };

        this.state.showVariantModal = true;
    }
    
    formatAttributesForDisplay(attributes) {
        if (!attributes) return [];
        
        const formattedAttrs = [];
        for (const [attrId, valueId] of Object.entries(attributes)) {
            const attribute = this.state.attributes.find(a => a.id === parseInt(attrId));
            if (attribute) {
                const value = attribute.values.find(v => v.id === valueId);
                if (value) {
                    formattedAttrs.push({
                        name: attribute.name,
                        value: value.display_name || value.name
                    });
                }
            }
        }
        
        return formattedAttrs;
    }

    closeVariantModal() {
        this.state.showVariantModal = false;
        this.state.selectedVariant = null;
    }
    
    getFilteredProducts() {
        return this.state.filteredProducts;
    }
    
    _createAttributeMatrix(product) {
        if (this.state.attributes.length < 2 || !product.variants || !product.variants.length) {
            return null;
        }
        
        const primaryAttr = this.state.attributes[0];
        const secondaryAttr = this.state.attributes[1];
        
        if (!primaryAttr || !secondaryAttr) {
            return null;
        }

        const matrix = {
            rows: [],
            column_headers: []
        };
        
        const primaryValues = new Set();
        const secondaryValues = new Set();
        
        product.variants.forEach(variant => {
            if (variant.attributes && variant.attributes[primaryAttr.id] !== undefined) {
                const primaryValueId = variant.attributes[primaryAttr.id];
                const primaryValue = primaryAttr.values.find(v => v.id === primaryValueId);
                if (primaryValue) {
                    primaryValues.add(primaryValue.name);
                }
            }
            
            if (variant.attributes && variant.attributes[secondaryAttr.id] !== undefined) {
                const secondaryValueId = variant.attributes[secondaryAttr.id];
                const secondaryValue = secondaryAttr.values.find(v => v.id === secondaryValueId);
                if (secondaryValue) {
                    secondaryValues.add(secondaryValue.name);
                }
            }
        });
        
        matrix.column_headers = Array.from(secondaryValues).sort();
        const rowHeaders = Array.from(primaryValues).sort();
        
        rowHeaders.forEach(primaryValueName => {
            const row = {
                header: primaryValueName,
                cells: []
            };
            
            matrix.column_headers.forEach(secondaryValueName => {
                const variant = product.variants.find(v => {
                    const primaryAttrId = primaryAttr.id;
                    const secondaryAttrId = secondaryAttr.id;
                    
                    if (!v.attributes || !v.attributes[primaryAttrId] || !v.attributes[secondaryAttrId]) {
                        return false;
                    }
                    
                    const primaryValueId = v.attributes[primaryAttrId];
                    const secondaryValueId = v.attributes[secondaryAttrId];
                    
                    const primaryValue = primaryAttr.values.find(val => val.id === primaryValueId);
                    const secondaryValue = secondaryAttr.values.find(val => val.id === secondaryValueId);
                    
                    if (!primaryValue || !secondaryValue) {
                        return false;
                    }
                    
                    return primaryValue.name === primaryValueName && 
                           secondaryValue.name === secondaryValueName;
                });
                
                if (variant) {
                    row.cells.push({
                        qty: variant.qty,
                        variant: variant
                    });
                } else {
                    row.cells.push(null);
                }
            });
            
            matrix.rows.push(row);
        });
        
        return matrix;
    }

    updateProductImage(productId, variantId) {
        const product = this.state.products.find(p => p.id === productId);
        if (!product) return;

        const variant = product.variants.find(v => v.id === variantId);
        if (!variant) return;

        const productImage = document.querySelector(`.product-image[data-product-id="${productId}"]`);
        if (productImage) {
            productImage.src = variant.image_url || product.image_url;
        }
    }

    getVariantCellClass(cell) {
        if (!cell) return 'empty-cell';
        if (!cell.variant) return 'no-variant-cell';
        if (cell.qty < 0) return 'negative-qty-cell';
        if (cell.qty === 0) return 'zero-qty-cell';
        if (cell.qty > 0) return 'positive-qty-cell';
        return '';
    }
    
    handleCellClick(cell, productId) {
        if (cell && cell.variant) { 
            this.showVariantDetails(cell.variant); 
            this.updateProductImage(productId, cell.variant.id);
        }
    }
    
    handleVariantClick(variant, productId) {
        this.showVariantDetails(variant);
        this.updateProductImage(productId, variant.id);
    }
} 