/* 文件槽的共享描述：类型定义 + 已解析摘要文案。
   「BOM 校对 · 文件与规则」与「BOM 生成 · 文件与模板」两页共用。 */

(function () {
  'use strict';

  var BOM = window.BOM;

  var KINDS = {
    schematic: {
      kind: 'schematic',
      label: '原理图',
      icon: 'file-code-2',
      accept: '.SchDoc,.schdoc,.SchDot',
      title: '拖入或点击上传原理图',
      note: 'Altium .SchDoc；解析 FileHeader 提取位号、Value / Comment 与 PCB 模型封装'
    },
    pcb: {
      kind: 'pcb',
      label: 'PCB',
      icon: 'circuit-board',
      accept: '.PcbDoc,.pcbdoc',
      title: '拖入或点击上传 PCB',
      note: 'Altium .PcbDoc；以 Components6/Data 的 PATTERN 作为封装基准'
    },
    bom: {
      kind: 'bom',
      label: '待核对 BOM',
      icon: 'table-2',
      accept: '.xlsx,.xlsm,.csv',
      title: '拖入或点击上传待核对 BOM',
      note: '需要核对的问题 BOM；读取项次、物料编码、名称、规格、用量与位置号'
    },
    master: {
      kind: 'master',
      label: '物料总表',
      icon: 'table-2',
      accept: '.xlsx,.xlsm,.csv',
      title: '拖入或点击上传物料总表',
      note: '支持 ERP 导出的 .xlsx；提供编码基准，用于「编码不存在」与「名称与总表不符」两类核对'
    },
    template: {
      kind: 'template',
      label: 'BOM 模板',
      icon: 'file-spreadsheet',
      accept: '.xlsx,.xlsm',
      title: '拖入或点击上传 BOM 模板',
      note: '模板只决定列结构、字段名称、格式与固定值，不会沿用模板内的物料内容与位号'
    }
  };

  function describe(kind, upload) {
    if (!upload) { return ''; }
    var s = upload.summary || {};
    var size = BOM.formatSize(upload.size);
    switch (kind) {
      case 'schematic':
        return size + ' · ' + (s.format || '设计文件') + ' · FileHeader 记录 ' +
          BOM.formatNumber(s.records) + ' 条 · 解析出 ' + BOM.formatNumber(s.components) + ' 个元件';
      case 'pcb':
        return size + ' · Components6/Data 元件 ' + BOM.formatNumber(s.components) +
          ' 个 · 封装 ' + BOM.formatNumber(s.patterns) + ' 种 · ' +
          BOM.formatNumber(s.unlabeled) + ' 个无位号';
      case 'bom':
        return size + ' · 明细行 ' + BOM.formatNumber(s.detailRows) + ' · 父级行 ' +
          BOM.formatNumber(s.groupRows) + ' · 残缺空行 ' + BOM.formatNumber(s.incompleteRows) +
          ' · 位号 ' + BOM.formatNumber(s.refCount) + ' 个';
      case 'master':
        return size + ' · ' + BOM.formatNumber(s.count) + ' 条 · 有效 ' +
          BOM.formatNumber(s.valid) + ' · 禁用 ' + BOM.formatNumber(s.disabled);
      case 'template':
        return size + ' · ' + BOM.formatNumber(s.columnCount) + ' 列 · 表头第 ' +
          BOM.formatNumber(s.headerRow) + ' 行' +
          (s.freeze ? ' · 冻结首行' : '') + (s.filter ? ' · 含筛选' : '');
      default:
        return size;
    }
  }

  function tag(upload) {
    if (!upload) { return { text: '待解析', cls: 'ck-tag--pending' }; }
    if (upload.status === '已解析') { return { text: '已解析', cls: 'ck-tag--success' }; }
    if (upload.status === '解析失败') { return { text: '解析失败', cls: 'ck-tag--error' }; }
    return { text: '待解析', cls: 'ck-tag--pending' };
  }

  BOM.slots = { KINDS: KINDS, describe: describe, tag: tag };
})();
