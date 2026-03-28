---
description: "Use when building Vue components or UI features with PrimeVue. Covers available components, import rules, and documentation URLs."
applyTo: "**/*.vue"
---

# PrimeVue Component Guidelines

Always use a PrimeVue component when one exists for the UI element being implemented.
Never use plain HTML elements (`<button>`, `<input>`, `<select>`, `<textarea>`, etc.) when an equivalent PrimeVue component is available.
Import PrimeVue components from `primevue/<component-name>`.

## Available Components (with doc URLs)

| Component | Import | Doc |
|-----------|--------|-----|
| Accordion | `primevue/accordion` | https://primevue.org/accordion |
| AutoComplete | `primevue/autocomplete` | https://primevue.org/autocomplete |
| Avatar | `primevue/avatar` | https://primevue.org/avatar |
| Badge | `primevue/badge` | https://primevue.org/badge |
| BlockUI | `primevue/blockui` | https://primevue.org/blockui |
| Breadcrumb | `primevue/breadcrumb` | https://primevue.org/breadcrumb |
| Button | `primevue/button` | https://primevue.org/button |
| Card | `primevue/card` | https://primevue.org/card |
| Carousel | `primevue/carousel` | https://primevue.org/carousel |
| CascadeSelect | `primevue/cascadeselect` | https://primevue.org/cascadeselect |
| Chart | `primevue/chart` | https://primevue.org/chart |
| Checkbox | `primevue/checkbox` | https://primevue.org/checkbox |
| Chip | `primevue/chip` | https://primevue.org/chip |
| ColorPicker | `primevue/colorpicker` | https://primevue.org/colorpicker |
| ConfirmDialog | `primevue/confirmdialog` | https://primevue.org/confirmdialog |
| ConfirmPopup | `primevue/confirmpopup` | https://primevue.org/confirmpopup |
| ContextMenu | `primevue/contextmenu` | https://primevue.org/contextmenu |
| DataTable | `primevue/datatable` | https://primevue.org/datatable |
| DataView | `primevue/dataview` | https://primevue.org/dataview |
| DatePicker | `primevue/datepicker` | https://primevue.org/datepicker |
| DeferredContent | `primevue/deferredcontent` | https://primevue.org/deferredcontent |
| Dialog | `primevue/dialog` | https://primevue.org/dialog |
| Divider | `primevue/divider` | https://primevue.org/divider |
| Dock | `primevue/dock` | https://primevue.org/dock |
| Drawer | `primevue/drawer` | https://primevue.org/drawer |
| Editor | `primevue/editor` | https://primevue.org/editor |
| Fieldset | `primevue/fieldset` | https://primevue.org/fieldset |
| FileUpload | `primevue/fileupload` | https://primevue.org/fileupload |
| FloatLabel | `primevue/floatlabel` | https://primevue.org/floatlabel |
| Fluid | `primevue/fluid` | https://primevue.org/fluid |
| Galleria | `primevue/galleria` | https://primevue.org/galleria |
| IconField | `primevue/iconfield` | https://primevue.org/iconfield |
| IftaLabel | `primevue/iftalabel` | https://primevue.org/iftalabel |
| Image | `primevue/image` | https://primevue.org/image |
| ImageCompare | `primevue/imagecompare` | https://primevue.org/imagecompare |
| Inplace | `primevue/inplace` | https://primevue.org/inplace |
| InputGroup | `primevue/inputgroup` | https://primevue.org/inputgroup |
| InputMask | `primevue/inputmask` | https://primevue.org/inputmask |
| InputNumber | `primevue/inputnumber` | https://primevue.org/inputnumber |
| InputOtp | `primevue/inputotp` | https://primevue.org/inputotp |
| InputText | `primevue/inputtext` | https://primevue.org/inputtext |
| Knob | `primevue/knob` | https://primevue.org/knob |
| Listbox | `primevue/listbox` | https://primevue.org/listbox |
| MegaMenu | `primevue/megamenu` | https://primevue.org/megamenu |
| Menu | `primevue/menu` | https://primevue.org/menu |
| Menubar | `primevue/menubar` | https://primevue.org/menubar |
| Message | `primevue/message` | https://primevue.org/message |
| MeterGroup | `primevue/metergroup` | https://primevue.org/metergroup |
| MultiSelect | `primevue/multiselect` | https://primevue.org/multiselect |
| OrderList | `primevue/orderlist` | https://primevue.org/orderlist |
| OrganizationChart | `primevue/organizationchart` | https://primevue.org/organizationchart |
| Paginator | `primevue/paginator` | https://primevue.org/paginator |
| Panel | `primevue/panel` | https://primevue.org/panel |
| PanelMenu | `primevue/panelmenu` | https://primevue.org/panelmenu |
| Password | `primevue/password` | https://primevue.org/password |
| PickList | `primevue/picklist` | https://primevue.org/picklist |
| Popover | `primevue/popover` | https://primevue.org/popover |
| ProgressBar | `primevue/progressbar` | https://primevue.org/progressbar |
| ProgressSpinner | `primevue/progressspinner` | https://primevue.org/progressspinner |
| RadioButton | `primevue/radiobutton` | https://primevue.org/radiobutton |
| Rating | `primevue/rating` | https://primevue.org/rating |
| ScrollPanel | `primevue/scrollpanel` | https://primevue.org/scrollpanel |
| ScrollTop | `primevue/scrolltop` | https://primevue.org/scrolltop |
| Select | `primevue/select` | https://primevue.org/select |
| SelectButton | `primevue/selectbutton` | https://primevue.org/selectbutton |
| Skeleton | `primevue/skeleton` | https://primevue.org/skeleton |
| Slider | `primevue/slider` | https://primevue.org/slider |
| SpeedDial | `primevue/speeddial` | https://primevue.org/speeddial |
| SplitButton | `primevue/splitbutton` | https://primevue.org/splitbutton |
| Splitter | `primevue/splitter` | https://primevue.org/splitter |
| Stepper | `primevue/stepper` | https://primevue.org/stepper |
| Tabs | `primevue/tabs` | https://primevue.org/tabs |
| Tag | `primevue/tag` | https://primevue.org/tag |
| Terminal | `primevue/terminal` | https://primevue.org/terminal |
| Textarea | `primevue/textarea` | https://primevue.org/textarea |
| TieredMenu | `primevue/tieredmenu` | https://primevue.org/tieredmenu |
| Timeline | `primevue/timeline` | https://primevue.org/timeline |
| Toast | `primevue/toast` | https://primevue.org/toast |
| ToggleButton | `primevue/togglebutton` | https://primevue.org/togglebutton |
| ToggleSwitch | `primevue/toggleswitch` | https://primevue.org/toggleswitch |
| Toolbar | `primevue/toolbar` | https://primevue.org/toolbar |
| Tree | `primevue/tree` | https://primevue.org/tree |
| TreeSelect | `primevue/treeselect` | https://primevue.org/treeselect |
| TreeTable | `primevue/treetable` | https://primevue.org/treetable |
| VirtualScroller | `primevue/virtualscroller` | https://primevue.org/virtualscroller |

## Directives

| Directive | Import | Doc |
|-----------|--------|-----|
| AnimateOnScroll | `primevue/animateonscroll` | https://primevue.org/animateonscroll |
| FocusTrap | `primevue/focustrap` | https://primevue.org/focustrap |
| KeyFilter | `primevue/keyfilter` | https://primevue.org/keyfilter |
| Ripple | `primevue/ripple` | https://primevue.org/ripple |
| StyleClass | `primevue/styleclass` | https://primevue.org/styleclass |
| Tooltip | `primevue/tooltip` | https://primevue.org/tooltip |

When in doubt about a component's API (props, events, slots), fetch the doc URL above before implementing.
