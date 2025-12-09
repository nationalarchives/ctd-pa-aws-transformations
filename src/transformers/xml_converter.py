"""
XML to JSON converter transformer.
"""
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

from .base import BaseTransformer


class XMLConverterTransformer(BaseTransformer):
    """
    Converts XML data to a structured JSON format.
    
    Config parameters:
        remove_empty_fields: If True, removes fields with null values and empty lists/dicts. (default: True)
    """

    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Convert XML string to a dictionary of JSON records.
        
        Args:
            data: XML string to convert.
            config: May contain 'remove_empty_fields'.
            context: Runtime context (not used).
            
        Returns:
            A dictionary where keys are IAIDs and values are the converted JSON records.
        """
        if not isinstance(data, str):
            raise ValueError(f"XMLConverterTransformer expects string input, got {type(data)}")

        remove_empty_fields = config.get('remove_empty_fields', True)
        
        logic = XMLConverterLogic(remove_empty_fields=remove_empty_fields)
        return logic.convert(data)


class XMLConverterLogic:
    def __init__(self, remove_empty_fields: bool = True):
        self.remove_empty_fields = remove_empty_fields
        self.record_level_mapping = {
            'FONDS': 1, 'SUB-FONDS': 2, 'SUB-SUB-FONDS': 3,
            'SUB-SUB-SUB-FONDS': 4, 'SUB-SUB-SUB-SUB-FONDS': 5,
            'SERIES': 6, 'SUB-SERIES': 7, 'SUB-SUB-SERIES': 8,
            'FILE': 9, 'ITEM': 10
        }

    def _clean_none(self, obj: Any) -> Optional[Any]:
        """Recursively remove None values and empty containers from an object."""
        if obj is None:
            return None
        if isinstance(obj, dict):
            new_dict = {k: self._clean_none(v) for k, v in obj.items() if v is not None}
            return {k: v for k, v in new_dict.items() if v is not None and (isinstance(v, (dict, list)) and len(v) > 0 or not isinstance(v, (dict, list)))} or None
        if isinstance(obj, list):
            new_list = [self._clean_none(item) for item in obj]
            return [item for item in new_list if item is not None and (isinstance(item, (dict, list)) and len(item) > 0 or not isinstance(item, (dict, list)))] or None
        return obj

    def convert(self, xml_string: str) -> Dict[str, Any]:
        """Parses an XML string and converts it to a dictionary of records."""
        root = ET.fromstring(xml_string)

        # Perform transformations directly on the XML tree
        self._transform_record_types(root)
        self._transform_client_filepaths(root)
        self._transform_dates(root)
        self._transform_languages(root)

        # Build a lookup for parentId resolution
        object_number_to_calm_id = self._build_object_number_lookup(root)

        records = {}
        for record_element in root.iter('record'):
            iaid_elem = record_element.find("Alternative_number/[alternative_number.type='CALM RecordID']/alternative_number")
            iaid = iaid_elem.text if iaid_elem is not None else None
            
            if not iaid:
                continue

            record_data = self._process_record(record_element, object_number_to_calm_id)
            
            if self.remove_empty_fields:
                cleaned_record = self._clean_none({"record": record_data})
                records[iaid] = cleaned_record if cleaned_record else {"record": {}}
            else:
                records[iaid] = {"record": record_data}
        
        return records

    def _transform_record_types(self, root: ET.Element):
        for record_type in root.iter('record_type'):
            neutral_value = record_type.find("./value[@lang='neutral']")
            if neutral_value is not None and neutral_value.text:
                key = neutral_value.text.strip()
                if key in self.record_level_mapping:
                    neutral_value.text = str(self.record_level_mapping[key])

    def _transform_client_filepaths(self, root: ET.Element):
        for client_filepath in root.iter('client_filepath'):
            if client_filepath.text:
                client_filepath.text = "Original filepath:" + client_filepath.text.strip()

    def _transform_dates(self, root: ET.Element):
        date_pattern = r"(\d{4})-(\d{2})-(\d{2})"
        replacement_pattern = r"\1\2\3"
        for date_element in root.iter('dating.date.start'):
            if date_element.text:
                date_element.text = re.sub(date_pattern, replacement_pattern, date_element.text)
        for date_element in root.iter('dating.date.end'):
            if date_element.text:
                date_element.text = re.sub(date_pattern, replacement_pattern, date_element.text)

    def _transform_languages(self, root: ET.Element):
        for language in root.iter('inscription.language'):
            if language.text:
                languages = [lang.strip() for lang in language.text.split(';')]
                if len(languages) > 1:
                    language.text = ', '.join(sorted(languages[:-1])) + ' and ' + languages[-1]

    def _build_object_number_lookup(self, root: ET.Element) -> Dict[str, str]:
        lookup = {}
        for record in root.iter('record'):
            obj_num_elem = record.find("object_number")
            calm_id_elem = record.find("Alternative_number/[alternative_number.type='CALM RecordID']/alternative_number")
            if obj_num_elem is not None and obj_num_elem.text and calm_id_elem is not None and calm_id_elem.text:
                lookup[obj_num_elem.text] = calm_id_elem.text
        return lookup

    def _process_record(self, record: ET.Element, obj_num_lookup: Dict[str, str]) -> Dict[str, Any]:
        """Extracts and structures data from a single <record> element."""
        
        def get_text(path: str, root=record) -> Optional[str]:
            elem = root.find(path)
            return elem.text.strip() if elem is not None and elem.text else None

        def get_all_text(path: str, root=record) -> list[str]:
            return [elem.text.strip() for elem in root.findall(path) if elem.text]

        iaid = get_text("Alternative_number/[alternative_number.type='CALM RecordID']/alternative_number")
        citable_reference = get_text("object_number")
        
        part_of_reference = get_text("Part_of/part_of_reference")
        parent_id = obj_num_lookup.get(part_of_reference, "A13530124")

        catalogue_level_str = get_text("record_type/value[@lang='neutral']")
        catalogue_level = int(catalogue_level_str) if catalogue_level_str and catalogue_level_str.isdigit() else 0

        access_conditions = "Open unless otherwise stated" if catalogue_level <= 8 else None

        arrangement_system = get_text("system_of_arrangement") or ''
        client_filepath = get_text("client_filepath") or ''
        arrangement = f"{arrangement_system} {client_filepath}".strip() or None

        covering_from_date_str = get_text("Dating/dating.date.start")
        covering_from_date = int(covering_from_date_str) if covering_from_date_str else None
        
        covering_to_date_str = get_text("Dating/dating.date.end")
        covering_to_date = int(covering_to_date_str) if covering_to_date_str else None

        held_by_info = get_text("institution.name")
        held_by = []
        if held_by_info == "The National Archives, Kew":
            held_by = [{"xReferenceId": "A13530124", "xReferenceCode": "66", "xReferenceName": "The National Archives, Kew"}]
        elif held_by_info == "UK Parliament":
            held_by = [{"xReferenceId": "A13531051", "xReferenceCode": "61", "xReferenceName": "UK Parliament"}]
        elif held_by_info == "British Film Institute (BFI) National Archive":
            held_by = [{"xReferenceId": "A13532152", "xReferenceCode": "2870", "xReferenceName": "British Film Institute (BFI) National Archive"}]

        closure_status_val = get_text("access_status/value[@lang='neutral']")
        closure_status, closure_code, closure_type, record_opening_date = None, None, None, None

        if catalogue_level >= 9:
            if closure_status_val == 'OPEN':
                closure_status = 'O'
            elif closure_status_val == 'CLOSED':
                closure_status = 'D'
            
            if closure_status == 'D':
                closed_until = get_text("closed_until")
                if closed_until:
                    try:
                        closure_code = ET.datetime.strptime(closed_until, "%Y-%m-%d").strftime("%Y")
                        record_opening_date = closed_until
                    except ValueError:
                        pass # Keep as None if format is wrong
                closure_type = 'U'

            if held_by_info == "UK Parliament":
                closure_status = 'U'
                closure_code = None
                closure_type = None
                record_opening_date = None
        
        copies_info_desc = get_text("existence_of_copies")
        copies_information = [{"description": copies_info_desc}] if copies_info_desc else []

        creator_name = []
        if catalogue_level <= 8:
            for prod_elem in record.findall("Production"):
                creator_elem = prod_elem.find("creator")
                if creator_elem is not None and creator_elem.text:
                    creator_name.append({"xReferenceName": creator_elem.text})

        digitised_val = get_text("digitised")
        digitised = digitised_val == "x"

        extent_descriptions = []
        for extent in record.findall('Extent'):
            value = get_text("extent.value", root=extent) or ""
            form = get_text("extent.form", root=extent) or ""
            if value or form:
                extent_descriptions.append((value, form))
        
        physical_description_extent = extent_descriptions[0][0] if extent_descriptions else None
        physical_description_form = '; '.join([f"{v} {f}".strip() for v, f in extent_descriptions]) if extent_descriptions else None

        reference_part_match = re.search(r"([^\/]+$)", citable_reference) if citable_reference else None
        reference_part = reference_part_match.group(1) if reference_part_match else None

        record_data = {
            "iaid": iaid,
            "citableReference": citable_reference,
            "parentId": parent_id,
            "accruals": get_text("accruals"),
            "accessConditions": access_conditions,
            "administrativeBackground": get_text("admin_history"),
            "arrangement": arrangement,
            "catalogueId": int(get_text("catid")) if get_text("catid") else None,
            "catalogueLevel": catalogue_level,
            "coveringFromDate": covering_from_date,
            "coveringToDate": covering_to_date,
            "chargeType": 1,
            "coveringDates": get_text("dating.notes"),
            "custodialHistory": get_text("object_history_note"),
            "closureCode": closure_code,
            "closureStatus": closure_status,
            "closureType": closure_type,
            "recordOpeningDate": record_opening_date,
            "copiesInformation": copies_information,
            "creatorName": creator_name or None,
            "digitised": digitised,
            "formerReferenceDep": get_text("Alternative_number/[alternative_number.type='Former reference (Department)']/alternative_number"),
            "formerReferencePro": get_text("Alternative_number/[alternative_number.type='Former archival reference']/alternative_number"),
            "heldBy": held_by,
            "language": get_text("Inscription//inscription.language"),
            "legalStatus": get_text("legal_status/value[@lang='0']"),
            "locationOfOriginals": [{"xReferenceDescription": get_text("existence_of_originals")}] if get_text("existence_of_originals") else [],
            "physicalDescriptionExtent": physical_description_extent,
            "physicalDescriptionForm": physical_description_form,
            "referencePart": reference_part,
            "publicationNote": get_all_text("publication_note"),
            "relatedMaterial": [{"description": get_text("related_material.free_text")}] if get_text("related_material.free_text") else [],
            "separatedMaterial": [],
            "restrictionsOnUse": "This record is not currently accessible in a playable format and is unavailable for public viewing" if not digitised and held_by_info == "British Film Institute (BFI) National Archive" else None,
            "scopeContent": {"description": get_text("Content_description/content.description")},
            "source": "PA",
            "title": get_text("Title/title"),
            "unpublishedFindingAids": get_all_text("Finding_aids/finding_aids"),
        }
        
        return record_data
