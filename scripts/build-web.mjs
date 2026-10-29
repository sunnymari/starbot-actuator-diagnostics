import {cp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
await rm('dist',{recursive:true,force:true});await mkdir('dist',{recursive:true});
await cp('viz/web','dist',{recursive:true});
await cp('diagnostics/rules.json','dist/diagnostic-rules.json');
const index=await readFile('dist/index.html','utf8');
await writeFile('dist/index.html',index.replace('<html lang="en">','<html lang="en" data-runtime="browser">'));
console.log('Built isolated browser demo in dist/; local Python CAN mode is unchanged.');
