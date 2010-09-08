#include <fstream>
#include <sstream>

#include "clb/Core/clbAssert.h"
#include "clb/Network/SerializationStructCompiler.h"

using namespace std;

std::string SerializationStructCompiler::ParseToValidCSymbolName(const char *str)
{
	stringstream ss;
	size_t len = strlen(str);
	for(size_t i = 0; i < len; ++i)
		if ((isalpha(str[i]) || (ss.str().length() > 0 && isdigit(str[i]))) && str[i] != ' ')
			ss << str[i];

	return ss.str();
}

void SerializationStructCompiler::WriteFilePreamble(std::ofstream &out)
{
	// Write the preamble of the file.
	out << "#pragma once" << endl
	    << endl
	    << "#include \"clb/Network/DataDeserializer.h\"" << endl
	    << "#include \"clb/Network/DataSerializer.h\"" << endl
	    << endl;
}

void SerializationStructCompiler::WriteMemberDefinition(const SerializedElementDesc &elem, int level, std::ofstream &out)
{
	string type = SerialTypeToString(elem.type); ///\todo What if type == struct?
	string name = ParseToValidCSymbolName(elem.name.c_str());

	if (elem.type == SerialStruct)
		type = string("S_") + name; ///\todo Add a ClassName parameter for better control over naming here?

	if (elem.varyingCount == true)
		out << Indent(level) << "std::vector<" << type << "> " << name << ";" << endl;
	else if (elem.count > 1)
		out << Indent(level) << type << " " << name << "[" << elem.count << "];" << endl;
	else
		out << Indent(level) << type << " " << name << ";" << endl;
}

void SerializationStructCompiler::WriteStructMembers(const SerializedElementDesc &elem, int level, std::ofstream &out)
{
	assert(&elem && elem.type == SerialStruct);

	int childStructIndex = 1;

	for(size_t i = 0; i < elem.elements.size(); ++i)
	{
		SerializedElementDesc &e = *elem.elements[i];
		assert(&e);

		WriteMemberDefinition(e, level, out);
	}
	out << endl;
}

void SerializationStructCompiler::WriteNestedStructs(const SerializedElementDesc &elem, int level, std::ofstream &out)
{
	assert(&elem && elem.type == SerialStruct);

	for(size_t i = 0; i < elem.elements.size(); ++i)
	{
		SerializedElementDesc &e = *elem.elements[i];
		assert(&e);

		if (e.type == SerialStruct)
			WriteStruct(e, level, out);
	}
}

void SerializationStructCompiler::WriteStructSizeMemberFunction(const SerializedElementDesc &elem, int level, std::ofstream &out)
{
	assert(&elem && elem.type == SerialStruct);

	out << Indent(level) << "inline size_t Size() const" << endl
		<< Indent(level) << "{" << endl
		<< Indent(level+1) << "return ";

	for(size_t i = 0; i < elem.elements.size(); ++i)
	{
		SerializedElementDesc &e = *elem.elements[i];
		assert(&e);

		if (i > 0)
			out << " + ";

		string memberName = ParseToValidCSymbolName(e.name.c_str());

		if (e.varyingCount)
		{
            if (e.count == 8)
                out << "1 + ";
            else if (e.count == 16)
                out << "2 + ";
            else if (e.count == 32)
                out << "4 + ";
            else
                out << "1 /* Warning: unsupported varyingCount bit amount */ + ";
        }

		if (e.type == SerialStruct)
		{
			if (e.varyingCount)
				out << "SumArray(" << memberName << ", " << memberName << ".size())";
			else if (e.count > 1)
				out << "SumArray(" << memberName << ", " << e.count << ")";
			else
				out << memberName << ".Size()";
		}
		else
		{
			if (e.varyingCount)
				out << memberName << ".size()" << "*" << SerialTypeSize(e.type);
			else if (e.count > 1)
				out << e.count << "*" << SerialTypeSize(e.type);
			else
				out << SerialTypeSize(e.type);
		}
	}

	if (elem.elements.size() == 0)
		out << "0";

	out << ";" << endl
		<< Indent(level) << "}" << endl << endl;
}

void SerializationStructCompiler::WriteSerializeMemberFunction(const SerializedElementDesc &elem, int level, std::ofstream &out)
{
	assert(&elem && elem.type == SerialStruct);

	out << Indent(level) << "inline void SerializeTo(DataSerializer &dst) const" << endl
		<< Indent(level) << "{" << endl;

	++level;

	for(size_t i = 0; i < elem.elements.size(); ++i)
	{
		SerializedElementDesc &e = *elem.elements[i];
		assert(&e);

		string memberName = ParseToValidCSymbolName(e.name.c_str());

		if (e.varyingCount == true)
		{
            if (e.count == 8)
                out << Indent(level) << "dst.Add<u8>(" << memberName << ".size());" << endl;
            else if (e.count == 16)
                out << Indent(level) << "dst.Add<u16>(" << memberName << ".size());" << endl;
            else if (e.count == 32)
                out << Indent(level) << "dst.Add<u32>(" << memberName << ".size());" << endl;
            else 
                out << Indent(level) << "dst.Add<u8>(" << memberName << ".size()); /* Warning: unsupported varyingCount bit amount */" << endl;
        }
        
		if (e.type == SerialStruct)
		{
			if (e.varyingCount == true)
			{
				out << Indent(level) << "for(size_t i = 0; i < " << memberName << ".size(); ++i)" << endl;
				out << Indent(level+1) << memberName << "[i].SerializeTo(dst);" << endl;
			}
			else if (e.count > 1)
			{
				out << Indent(level) << "for(size_t i = 0; i < " << e.count << "; ++i)" << endl;
				out << Indent(level+1) << memberName << "[i].SerializeTo(dst);" << endl;
			}
			else
				out << Indent(level) << memberName << ".SerializeTo(dst);" << endl;
		}
		else
		{
			if (e.varyingCount == true)
			{
				out << Indent(level) << "if (" << memberName << ".size() > 0)" << endl;
				out << Indent(level+1) << "dst.AddArray<" << SerialTypeToString(e.type) << ">(&" << memberName
					<< "[0], " << memberName << ".size());" << endl;
			}
			else if (e.count > 1)
				out << Indent(level) << "dst.AddArray<" << SerialTypeToString(e.type) << ">(" << memberName
					<< ", " << e.count << ");" << endl;
			else 
				out << Indent(level) << "dst.Add<" << SerialTypeToString(e.type) << ">(" << memberName
					<< ");" << endl;
		}
	}
	--level;
	out << Indent(level) << "}" << endl << endl;
}

void SerializationStructCompiler::WriteDeserializeMemberFunction(const SerializedElementDesc &elem, int level, std::ofstream &out)
{
	assert(&elem && elem.type == SerialStruct);

	out << Indent(level) << "inline void DeserializeFrom(DataDeserializer &src)" << endl
		<< Indent(level) << "{" << endl;

	++level;

	for(size_t i = 0; i < elem.elements.size(); ++i)
	{
		SerializedElementDesc &e = *elem.elements[i];
		assert(&e);

		string memberName = ParseToValidCSymbolName(e.name.c_str());

		if (e.varyingCount == true)
        {
            if (e.count == 8)
                out << Indent(level) << memberName << ".resize(src.Read<u8>());" << endl;
            else if (e.count == 16)
                out << Indent(level) << memberName << ".resize(src.Read<u16>());" << endl;
            else if (e.count == 32)
                out << Indent(level) << memberName << ".resize(src.Read<u32>());" << endl;
            else
                out << Indent(level) << memberName << ".resize(src.Read<u8>()); /* Warning: unsupported varyingCount bit amount */" << endl;
        }
		if (e.type == SerialStruct)
		{
			if (e.varyingCount == true)
			{
				out << Indent(level) << "for(size_t i = 0; i < " << memberName << ".size(); ++i)" << endl;
				out << Indent(level+1) << memberName << "[i].DeserializeFrom(src);" << endl;
			}
			else if (e.count > 1)
			{
				out << Indent(level) << "for(size_t i = 0; i < " << e.count << "; ++i)" << endl;
				out << Indent(level+1) << memberName << "[i].DeserializeFrom(src);" << endl;
			}
			else
				out << Indent(level) << memberName << ".DeserializeFrom(src);" << endl;
		}
		else
		{
			if (e.varyingCount == true)
			{
				out << Indent(level) << "if (" << memberName << ".size() > 0)" << endl;
				out << Indent(level+1) << "src.ReadArray<" << SerialTypeToString(e.type) << ">(&" << memberName
					<< "[0], " << memberName << ".size());" << endl;
			}
			else if (e.count > 1)
				out << Indent(level) << "src.ReadArray<" << SerialTypeToString(e.type) << ">(" << memberName
					<< ", " << e.count << ");" << endl;
			else 
				out << Indent(level) << memberName << " = src.Read<" << SerialTypeToString(e.type) << ">();" << endl;
		}
	}
	--level;
	out << Indent(level) << "}" << endl << endl;
}

void SerializationStructCompiler::WriteStruct(const SerializedElementDesc &elem, int level, std::ofstream &out)
{
	assert(&elem && elem.type == SerialStruct);

	string className = string("struct S_") + ParseToValidCSymbolName(elem.name.c_str());
	if (level == 0)
		className = string("struct ") + ParseToValidCSymbolName(elem.name.c_str());

	out << Indent(level) << className << endl
	    << Indent(level) << "{" << endl;

	WriteNestedStructs(elem, level+1, out);
	WriteStructMembers(elem, level+1, out);
	WriteStructSizeMemberFunction(elem, level+1, out);
	WriteSerializeMemberFunction(elem, level+1, out);
	WriteDeserializeMemberFunction(elem, level+1, out);
	out << Indent(level) << "};" << endl << endl;
}

void SerializationStructCompiler::CompileStruct(const SerializedElementDesc &structure, const char *outfile)
{
	ofstream out(outfile);

	WriteFilePreamble(out);
	WriteStruct(structure, 0, out);
}

void SerializationStructCompiler::WriteMessage(const SerializedMessageDesc &message, std::ofstream &out)
{
	string structName = string("Msg") + message.name;
	out << "struct " << structName << endl
		<< "{" << endl;

	out << Indent(1) << structName << "()" << endl 
		<< Indent(1) << "{" << endl
		<< Indent(2) << "InitToDefault();" << endl
		<< Indent(1) << "}" << endl << endl;

	out << Indent(1) << structName << "(const char *data, size_t numBytes)" << endl 
		<< Indent(1) << "{" << endl
		<< Indent(2) << "InitToDefault();" << endl
		<< Indent(2) << "DataDeserializer dd(data, numBytes);" << endl
		<< Indent(2) << "DeserializeFrom(dd);" << endl
		<< Indent(1) << "}" << endl << endl;

	out << Indent(1) << "void InitToDefault()" << endl
		<< Indent(1) << "{" << endl
		<< Indent(2) << "reliable = " << (message.reliable ? "true" : "false") << ";" << endl
		<< Indent(2) << "inOrder = " << (message.inOrder ? "true" : "false") << ";" << endl
		<< Indent(2) << "priority = " << message.priority << ";" << endl
		<< Indent(1) << "}" << endl << endl;

	out << Indent(1) << "static inline u32 MessageID() { return " << message.id << "; }" << endl;
	out << Indent(1) << "static inline const char *Name() { return \"" << message.name << "\"; }" << endl << endl;

	out << Indent(1) << "bool reliable;" << endl;
	out << Indent(1) << "bool inOrder;" << endl;
	out << Indent(1) << "u32 priority;" << endl << endl;

	WriteNestedStructs(*message.data, 1, out);
	WriteStructMembers(*message.data, 1, out);
	WriteStructSizeMemberFunction(*message.data, 1, out);
	WriteSerializeMemberFunction(*message.data, 1, out);
	WriteDeserializeMemberFunction(*message.data, 1, out);

	out << "};" << endl << endl;

}

void SerializationStructCompiler::CompileMessage(const SerializedMessageDesc &message, const char *outfile)
{
	ofstream out(outfile);

	WriteFilePreamble(out);
	WriteMessage(message, out);
}

std::string SerializationStructCompiler::Indent(int level)
{
	stringstream ss;
	for(int i = 0; i < level; ++i)
		ss << "\t";
	return ss.str();
}